"""
SegmentationOrchestrator: the brain of the MedSAM agent.

Responsibilities:
  1. Hold the current session state (volume, mask, prompts, organ).
  2. Coordinate model inference for prompted slices.
  3. Trigger 3D mask propagation.
  4. Manage multi-round refinement.
  5. Write all outputs (mask, overlays, logs).
  6. Expose a clean API for both the UI and CLI.

Design: the orchestrator is intentionally *stateful* and *single-session*.
For multi-session / batch use, create one orchestrator per case.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..io.nifti_reader import NiftiReader
from ..io import nifti_utils as _nu
from ..io.image_writer import (
    save_mask_nifti,
    save_overlay_png,
    save_overlay_grid,
    save_prompts_json,
    save_metrics_json,
)
from ..models.base_adapter import BaseSegAdapter, Prompt, SegResult
from ..core.propagation import Propagator
from ..core.session import Session
from .prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class SegmentationOrchestrator:
    """Manages the full lifecycle of one interactive segmentation session.

    Parameters
    ----------
    adapter:
        Loaded segmentation model adapter.
    output_dir:
        Root directory for all outputs.
    propagation_strategy:
        "sam_guided" | "interpolate" | "nearest"
    save_intermediates:
        Whether to save per-slice overlays during propagation.
    """

    def __init__(
        self,
        adapter: BaseSegAdapter,
        output_dir: str | Path = "output",
        propagation_strategy: str = "sam_guided",
        save_intermediates: bool = True,
    ):
        self.adapter = adapter
        self.output_dir = Path(output_dir)
        self.propagation_strategy = propagation_strategy
        self.save_intermediates = save_intermediates

        self._session: Optional[Session] = None
        self._reader: Optional[NiftiReader] = None
        self._prompt_manager: Optional[PromptManager] = None
        self._propagator: Optional[Propagator] = None
        self._mask_volume: Optional[np.ndarray] = None

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def new_session(
        self,
        volume_path: str | Path,
        organ: str = "custom",
        axis: int = 0,
        norm_method: str = "percentile",
        norm_kwargs: Optional[Dict[str, Any]] = None,
        gt_mask_path: Optional[str | Path] = None,
        case_id: Optional[str] = None,
    ) -> "SegmentationOrchestrator":
        """Initialize a new segmentation session.

        Parameters
        ----------
        volume_path:
            Path to NIfTI file.
        organ:
            Target organ name.
        axis:
            Primary viewing axis (0=axial).
        norm_method:
            Intensity normalization: "percentile" | "window" | "minmax".
        norm_kwargs:
            Extra kwargs for normalize_intensity.
        gt_mask_path:
            Optional ground-truth mask for evaluation.
        case_id:
            Identifier used for output directory naming.
            Defaults to volume filename stem.
        """
        volume_path = Path(volume_path)
        if case_id is None:
            case_id = volume_path.stem.replace(".nii", "")

        self._reader = NiftiReader(
            volume_path,
            norm_method=norm_method,
            norm_kwargs=norm_kwargs or {},
        ).load()

        shape = self._reader.shape
        self._mask_volume = np.zeros(shape, dtype=np.uint8)

        self._prompt_manager = PromptManager(organ=organ, axis=axis)

        self._propagator = Propagator(
            strategy=self.propagation_strategy,
            adapter=self.adapter,
        )

        gt_mask: Optional[np.ndarray] = None
        if gt_mask_path is not None:
            gt_vol, _, _ = _nu.load_nifti(gt_mask_path)
            gt_mask = gt_vol.astype(np.uint8)

        self._session = Session(
            case_id=case_id,
            volume_path=volume_path,
            organ=organ,
            axis=axis,
            volume_shape=shape,
            gt_mask=gt_mask,
            output_dir=self.output_dir / case_id,
        )
        self._session.case_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"New session: case={case_id}, organ={organ}, "
            f"shape={shape}, axis={axis}"
        )
        return self

    # ── Prompt management ─────────────────────────────────────────────────────

    def add_box_prompt(
        self,
        slice_idx: int,
        box: List[float],
        axis: Optional[int] = None,
    ) -> Prompt:
        """Add a box prompt and immediately run slice inference.

        Returns the prompt object.
        """
        self._require_session()
        p = self._prompt_manager.add_box(slice_idx, box, axis=axis)  # type: ignore[union-attr]
        logger.info(f"Box prompt added: slice={slice_idx}, box={box}")
        return p

    def add_point_prompt(
        self,
        slice_idx: int,
        x: float,
        y: float,
        label: int = 1,
        axis: Optional[int] = None,
    ) -> Prompt:
        """Add a point prompt (label=1 foreground, 0 background)."""
        self._require_session()
        p = self._prompt_manager.add_point(slice_idx, x, y, label, axis=axis)  # type: ignore[union-attr]
        logger.info(f"Point prompt added: slice={slice_idx}, pt=({x},{y}), label={label}")
        return p

    def remove_prompt(self, slice_idx: int, axis: Optional[int] = None) -> None:
        """Remove all prompts for a given slice."""
        self._require_session()
        self._prompt_manager.remove_slice(slice_idx, axis=axis)  # type: ignore[union-attr]

    # ── Inference ─────────────────────────────────────────────────────────────

    def segment_slice(self, slice_idx: int, axis: Optional[int] = None) -> np.ndarray:
        """Run inference on a single prompted slice.

        Returns the predicted binary mask for that slice (H, W).
        """
        self._require_session()
        assert self._reader is not None and self._mask_volume is not None

        ax = axis if axis is not None else self._prompt_manager.axis  # type: ignore[union-attr]
        prompts = self._prompt_manager.get_prompts_for_slice(slice_idx, axis=ax)  # type: ignore[union-attr]

        if not prompts:
            logger.warning(f"No prompts found for slice {slice_idx}. Skipping.")
            return self._get_mask_slice(slice_idx, ax)

        img_slice = self._reader.get_slice(slice_idx, axis=ax, normalized=True)
        best_result: Optional[SegResult] = None

        for prompt in prompts:
            result = self.adapter.predict_slice(img_slice, prompt)
            if best_result is None or (
                result.confidence is not None
                and best_result.confidence is not None
                and result.confidence > best_result.confidence
            ):
                best_result = result

        if best_result is not None:
            self._set_mask_slice(slice_idx, ax, best_result.mask)
            self._session.record_inference(slice_idx, best_result)  # type: ignore[union-attr]
            logger.info(
                f"Inference done: slice={slice_idx}, "
                f"mask_area={int(best_result.mask.sum())}"
            )

        return self._get_mask_slice(slice_idx, ax)

    def segment_all_prompted(self) -> Dict[int, np.ndarray]:
        """Run inference on every slice that has at least one prompt.

        Returns dict mapping slice_idx → mask (H, W).
        """
        self._require_session()
        results: Dict[int, np.ndarray] = {}
        for idx in self._prompt_manager.prompted_slices():  # type: ignore[union-attr]
            results[idx] = self.segment_slice(idx)
        return results

    def propagate_to_volume(self) -> np.ndarray:
        """Propagate prompted-slice segmentations to the full 3D volume.

        Strategy (see Propagator for details):
          1. Infer all prompted slices (if not already done).
          2. Propagate / interpolate to unprompted slices.

        Returns the full 3D binary mask (H, W, D).
        """
        self._require_session()
        assert self._reader is not None and self._mask_volume is not None

        # Infer all prompted slices first
        prompted = self._prompt_manager.prompted_slices()  # type: ignore[union-attr]
        if not prompted:
            raise RuntimeError("No prompts available. Add at least one box/point prompt first.")

        logger.info(f"Propagating volume: {len(prompted)} seed slices → full volume")
        t0 = time.time()

        for idx in prompted:
            self.segment_slice(idx)

        ax = self._prompt_manager.axis  # type: ignore[union-attr]
        n_total = self._reader.num_slices(axis=ax)

        self._mask_volume = self._propagator.propagate(  # type: ignore[union-attr]
            image_volume=self._reader.volume_norm,
            partial_mask=self._mask_volume,
            prompted_slices=prompted,
            axis=ax,
            n_total=n_total,
            prompt_manager=self._prompt_manager,
        )

        elapsed = time.time() - t0
        total_voxels = int(self._mask_volume.sum())
        logger.info(
            f"Propagation done in {elapsed:.1f}s: "
            f"{total_voxels} foreground voxels"
        )
        self._session.record_propagation(elapsed, total_voxels)  # type: ignore[union-attr]

        return self._mask_volume

    # ── Refinement ────────────────────────────────────────────────────────────

    def refine_slice(
        self,
        slice_idx: int,
        box: Optional[List[float]] = None,
        points: Optional[List[Tuple[float, float, int]]] = None,
        axis: Optional[int] = None,
    ) -> np.ndarray:
        """Refine existing segmentation on a slice with an additional prompt.

        Adds the new prompt and re-runs inference, combining with existing mask.
        """
        self._require_session()

        if box is not None:
            self.add_box_prompt(slice_idx, box, axis=axis)
        if points is not None:
            for x, y, lbl in points:
                self.add_point_prompt(slice_idx, x, y, lbl, axis=axis)

        return self.segment_slice(slice_idx, axis=axis)

    # ── Output ────────────────────────────────────────────────────────────────

    def save_outputs(
        self,
        save_mask: bool = True,
        save_overlay: bool = True,
        save_prompts: bool = True,
    ) -> Dict[str, Path]:
        """Write all session outputs to disk.

        Returns dict of {output_type: path}.
        """
        self._require_session()
        assert self._session is not None and self._reader is not None

        out: Dict[str, Path] = {}
        case_dir = self._session.case_dir

        # ── Mask ─────────────────────────────────────────────────────────
        if save_mask and self._mask_volume is not None:
            mask_path = case_dir / "pred_mask.nii.gz"
            save_mask_nifti(
                self._mask_volume,
                mask_path,
                reference_affine=self._reader.affine,
                reference_header=self._reader.header,
            )
            out["mask"] = mask_path
            logger.info(f"Mask saved: {mask_path}")

        # ── Overlay grid ─────────────────────────────────────────────────
        if save_overlay and self._mask_volume is not None:
            ax = self._prompt_manager.axis  # type: ignore[union-attr]
            overlay_path = case_dir / "overlay_grid.png"
            save_overlay_grid(
                self._reader.volume_norm,
                self._mask_volume,
                overlay_path,
                axis=ax,
                num_slices=8,
            )
            out["overlay_grid"] = overlay_path
            logger.info(f"Overlay grid saved: {overlay_path}")

        # ── Prompts JSON ──────────────────────────────────────────────────
        if save_prompts:
            prompts_path = case_dir / "prompts.json"
            save_prompts_json(
                self._prompt_manager.to_dict(),  # type: ignore[union-attr]
                prompts_path,
            )
            out["prompts"] = prompts_path
            logger.info(f"Prompts saved: {prompts_path}")

        # ── Session log ────────────────────────────────────────────────────
        log_path = case_dir / "session_log.json"
        self._session.save_log(log_path)
        out["log"] = log_path

        return out

    def compute_metrics(self) -> Optional[Dict[str, Any]]:
        """Compute evaluation metrics if GT mask is available.

        Returns None if no GT was provided (not an error condition).
        """
        self._require_session()
        assert self._session is not None

        if self._session.gt_mask is None:
            logger.info(
                "No ground-truth mask provided — metrics not computed. "
                "This is expected for purely inference-only sessions."
            )
            return None

        if self._mask_volume is None or not self._mask_volume.any():
            logger.warning("Mask volume is empty — cannot compute metrics.")
            return None

        from ..eval.metrics import compute_all_metrics

        gt = self._session.gt_mask
        pred = self._mask_volume

        # Align shapes (trim or pad if needed)
        if gt.shape != pred.shape:
            logger.warning(
                f"GT shape {gt.shape} != pred shape {pred.shape}. Skipping metrics."
            )
            return None

        spacing = self._reader.voxel_spacing()
        metrics = compute_all_metrics(pred, gt, voxel_spacing=spacing)

        metrics_path = self._session.case_dir / "metrics.json"
        save_metrics_json(metrics, metrics_path)
        logger.info(f"Metrics: {metrics}")
        return metrics

    # ── Convenience getters ───────────────────────────────────────────────────

    def get_slice_image(self, slice_idx: int, axis: int = 0) -> np.ndarray:
        self._require_session()
        return self._reader.get_slice(slice_idx, axis=axis, normalized=True)  # type: ignore[union-attr]

    def get_slice_mask(self, slice_idx: int, axis: int = 0) -> np.ndarray:
        self._require_session()
        return self._get_mask_slice(slice_idx, axis)

    def get_slice_overlay(
        self,
        slice_idx: int,
        axis: int = 0,
        alpha: float = 0.4,
        mask_color: Tuple[int, int, int] = (255, 215, 0),
    ) -> np.ndarray:
        """Return RGB overlay array (H, W, 3) for display."""
        from ..io.image_writer import save_overlay_png
        self._require_session()

        img = self.get_slice_image(slice_idx, axis=axis)
        mask = self.get_slice_mask(slice_idx, axis=axis)
        prompts_on_slice = self._prompt_manager.get_prompts_for_slice(  # type: ignore[union-attr]
            slice_idx, axis=axis
        )
        prompt_dicts = [p.to_dict() for p in prompts_on_slice]

        # Build RGB array in memory
        import numpy as np
        H, W = img.shape
        img_u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        rgb = np.stack([img_u8, img_u8, img_u8], axis=-1)

        if mask.any():
            mc = np.array(mask_color, dtype=np.float32)
            overlay = rgb.astype(np.float32)
            for c in range(3):
                overlay[:, :, c] = np.where(
                    mask.astype(bool),
                    (1 - alpha) * rgb[:, :, c] + alpha * mc[c],
                    rgb[:, :, c],
                )
            rgb = overlay.clip(0, 255).astype(np.uint8)

        # Draw prompts
        if prompt_dicts:
            from PIL import Image, ImageDraw
            pil_img = Image.fromarray(rgb)
            draw = ImageDraw.Draw(pil_img)
            for p in prompt_dicts:
                if p.get("box"):
                    x1, y1, x2, y2 = [int(v) for v in p["box"]]
                    draw.rectangle([x1, y1, x2, y2], outline=(0, 120, 255), width=2)
                if p.get("points"):
                    for pt in p["points"]:
                        x, y, lbl = int(pt[0]), int(pt[1]), pt[2]
                        color = (0, 255, 0) if lbl == 1 else (255, 0, 0)
                        r = 5
                        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
            rgb = np.array(pil_img)

        return rgb

    @property
    def session(self) -> Optional[Session]:
        return self._session

    @property
    def reader(self) -> Optional[NiftiReader]:
        return self._reader

    @property
    def mask_volume(self) -> Optional[np.ndarray]:
        return self._mask_volume

    @property
    def prompt_manager(self) -> Optional[PromptManager]:
        return self._prompt_manager

    # ── Private ───────────────────────────────────────────────────────────────

    def _require_session(self) -> None:
        if self._session is None:
            raise RuntimeError("No active session. Call new_session() first.")

    def _get_mask_slice(self, idx: int, axis: int) -> np.ndarray:
        assert self._mask_volume is not None
        return _nu.get_slice(self._mask_volume, idx, axis=axis)

    def _set_mask_slice(self, idx: int, axis: int, mask: np.ndarray) -> None:
        assert self._mask_volume is not None
        _nu.set_slice(self._mask_volume, idx, mask, axis=axis)
