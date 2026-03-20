"""
MedSAM2 adapter: wraps MedSAM2 (SAM2-based video propagation) for 3D medical
image segmentation.

MedSAM2 treats each CT/MRI volume as a video: a bounding-box (or point) prompt
is given on one or more seed slices, then `propagate_in_video` fills the rest
of the volume in one forward+reverse pass.

Reference: https://github.com/bowang-lab/MedSAM2
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch

from .base_adapter import BaseSegAdapter, Prompt, SegResult

logger = logging.getLogger(__name__)

# ─── Module-level model cache (single instance per process) ──────────────────
_MODEL_CACHE: Dict[str, Any] = {}


class MedSAM2Adapter(BaseSegAdapter):
    """Adapter wrapping MedSAM2 for box-prompted 3D segmentation.

    Usage
    -----
    >>> adapter = MedSAM2Adapter(device="cuda")
    >>> adapter.load_model(
    ...     checkpoint="/path/to/MedSAM2_latest.pt",
    ...     medsam2_repo_path="/path/to/MedSAM2",
    ... )
    >>> result = adapter.predict_slice(slice_img, prompt)
    """

    IMG_SIZE: int = 512
    IMG_MEAN = (0.485, 0.456, 0.406)
    IMG_STD  = (0.229, 0.224, 0.225)
    DEFAULT_CONFIG = "configs/sam2.1_hiera_t512.yaml"

    def __init__(
        self,
        device: str = "cuda",
        medsam2_repo_path: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(device=device, **kwargs)
        self._predictor: Any = None
        self._medsam2_repo = medsam2_repo_path or os.environ.get(
            "MEDSAM2_REPO_PATH", ""
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def load_model(
        self,
        checkpoint: str,
        medsam2_repo_path: Optional[str] = None,
        config_file: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Load MedSAM2 weights.

        Parameters
        ----------
        checkpoint:
            Path to MedSAM2 checkpoint (.pt file).
        medsam2_repo_path:
            Root of the MedSAM2 source tree.
            Required if MEDSAM2_REPO_PATH env var is not set.
        config_file:
            Hydra config name (relative to MedSAM2's sam2/ package).
            Defaults to "configs/sam2.1_hiera_t512.yaml".
        """
        repo = medsam2_repo_path or self._medsam2_repo
        if not repo:
            raise ValueError(
                "medsam2_repo_path is required for MedSAM2Adapter. "
                "Set MEDSAM2_REPO_PATH in .env or pass medsam2_repo_path."
            )
        repo = str(Path(repo).resolve())
        if not Path(repo).exists():
            raise FileNotFoundError(f"MedSAM2 repo not found: {repo}")

        checkpoint = str(checkpoint)
        if not Path(checkpoint).exists():
            raise FileNotFoundError(
                f"MedSAM2 checkpoint not found: {checkpoint}\n"
                "Download from: https://huggingface.co/bowang-lab/MedSAM2"
            )

        config_file = config_file or self.DEFAULT_CONFIG

        device = _resolve_device(self.device)
        cache_key = f"{checkpoint}_{device}"

        if cache_key in _MODEL_CACHE:
            self._predictor = _MODEL_CACHE[cache_key]
            self._loaded = True
            logger.info("MedSAM2: loaded from process cache.")
            return

        logger.info(f"MedSAM2: loading checkpoint {checkpoint} on {device}")
        self._predictor = _build_predictor(repo, config_file, checkpoint, str(device))
        _MODEL_CACHE[cache_key] = self._predictor
        self.device = str(device)
        self._loaded = True
        logger.info("MedSAM2: model ready.")

    # ── Core inference ────────────────────────────────────────────────────

    def predict_slice(
        self,
        image_slice: np.ndarray,
        prompt: Prompt,
    ) -> SegResult:
        """Segment a single 2D slice using a bounding-box prompt.

        Wraps the slice as a 1-frame video and uses MedSAM2's video predictor.

        Parameters
        ----------
        image_slice:
            Float32 [0, 1] array, shape (H, W).
        prompt:
            Must have prompt_type="box" and a valid box [x1, y1, x2, y2].
        """
        self._require_loaded()
        if prompt.box is None:
            raise ValueError("MedSAM2Adapter requires a bounding-box prompt.")

        H, W = image_slice.shape[:2]
        # Treat single slice as a 1-frame volume
        imgs_tensor = _prepare_imgs(
            image_slice[np.newaxis],  # (1, H, W)
            self.IMG_SIZE, self.IMG_MEAN, self.IMG_STD, self.device,
        )
        box = np.array(prompt.box, dtype=np.float32)

        ctx = _autocast_ctx(self.device)
        with torch.inference_mode(), ctx:
            inference_state = self._predictor.init_state(imgs_tensor, H, W)
            try:
                self._predictor.add_new_points_or_box(
                    inference_state=inference_state,
                    frame_idx=0,
                    obj_id=1,
                    box=box,
                )
                mask = np.zeros((H, W), dtype=np.uint8)
                for _, _, out_mask_logits in self._predictor.propagate_in_video(
                    inference_state
                ):
                    mask = (out_mask_logits[0] > 0.0).cpu().numpy()[0].astype(np.uint8)
            finally:
                self._predictor.reset_state(inference_state)

        confidence = float(mask.mean()) if mask.any() else 0.0
        return SegResult(
            slice_idx=prompt.slice_idx,
            mask=mask,
            confidence=confidence,
        )

    def predict_volume(
        self,
        image_volume: np.ndarray,
        prompts: List[Prompt],
        axis: int = 0,
    ) -> np.ndarray:
        """Segment the full 3D volume using MedSAM2's native video propagation.

        Performs one forward pass and one reverse pass with `propagate_in_video`,
        combining results with a logical OR so both directions fill the volume.

        Parameters
        ----------
        image_volume:
            Float32 [0, 1] volume of shape (H, W, D) (nifti_utils convention).
        prompts:
            Box prompts on seed slices.  Only box prompts are supported.
        axis:
            Axis along which to propagate (0=axial, 1=coronal, 2=sagittal).
        """
        self._require_loaded()
        if not prompts:
            return np.zeros(image_volume.shape, dtype=np.uint8)

        # Extract slices along the propagation axis → (n_slices, H, W)
        vol_axis, H_orig, W_orig = _extract_along_axis(image_volume, axis)
        n_slices = vol_axis.shape[0]

        imgs_tensor = _prepare_imgs(
            vol_axis, self.IMG_SIZE, self.IMG_MEAN, self.IMG_STD, self.device
        )

        mask_volume = np.zeros(image_volume.shape, dtype=np.uint8)

        ctx = _autocast_ctx(self.device)
        with torch.inference_mode(), ctx:
            inference_state = self._predictor.init_state(imgs_tensor, H_orig, W_orig)
            try:
                # ── Forward pass ──────────────────────────────────────────
                _add_prompts(self._predictor, inference_state, prompts)
                for out_frame_idx, _, out_mask_logits in self._predictor.propagate_in_video(
                    inference_state
                ):
                    m = (out_mask_logits[0] > 0.0).cpu().numpy()[0].astype(np.uint8)
                    _set_axis_slice(mask_volume, out_frame_idx, m, axis)

                self._predictor.reset_state(inference_state)

                # ── Reverse pass ──────────────────────────────────────────
                _add_prompts(self._predictor, inference_state, prompts)
                for out_frame_idx, _, out_mask_logits in self._predictor.propagate_in_video(
                    inference_state, reverse=True
                ):
                    m = (out_mask_logits[0] > 0.0).cpu().numpy()[0].astype(np.uint8)
                    cur = _get_axis_slice(mask_volume, out_frame_idx, axis)
                    _set_axis_slice(mask_volume, out_frame_idx, np.maximum(cur, m), axis)

            finally:
                self._predictor.reset_state(inference_state)

        logger.info(
            f"MedSAM2 predict_volume done: axis={axis}, "
            f"foreground_voxels={int(mask_volume.sum())}"
        )
        return mask_volume

    def refine_with_prompts(
        self,
        image_slice: np.ndarray,
        existing_mask: np.ndarray,
        new_prompt: Prompt,
    ) -> SegResult:
        return self.predict_slice(image_slice, new_prompt)


# ─── Private helpers ──────────────────────────────────────────────────────────


def _resolve_device(device_str: str) -> torch.device:
    if "cuda" in device_str and not torch.cuda.is_available():
        import warnings
        warnings.warn("CUDA not available, falling back to CPU.", stacklevel=3)
        return torch.device("cpu")
    try:
        return torch.device(device_str)
    except Exception:
        return torch.device("cpu")


def _build_predictor(repo: str, config_file: str, checkpoint: str, device: str) -> Any:
    """Import MedSAM2's sam2 package and build the video predictor.

    Inserts *repo* at the front of sys.path so MedSAM2's `sam2/` package
    takes precedence over any other `sam2` installation.  If a conflicting
    `sam2` module is already cached from a different path, it is cleared so
    that MedSAM2's `__init__.py` (which initialises Hydra) runs correctly.
    """
    _ensure_medsam2_sam2(repo)

    from sam2.build_sam import build_sam2_video_predictor_npz  # type: ignore

    predictor = build_sam2_video_predictor_npz(
        config_file, checkpoint, device=device
    )
    return predictor


def _ensure_medsam2_sam2(repo: str) -> None:
    """Make MedSAM2's sam2 package the active one in sys.modules."""
    # Put repo at the very front of sys.path
    if repo in sys.path:
        sys.path.remove(repo)
    sys.path.insert(0, repo)

    # If sam2 is already imported from a *different* location, evict it so
    # that re-importing resolves to MedSAM2's copy (which initialises Hydra).
    medsam2_sam2 = os.path.join(repo, "sam2")
    sam2_mod = sys.modules.get("sam2")
    if sam2_mod is not None:
        mod_file = getattr(sam2_mod, "__file__", "") or ""
        if not mod_file.startswith(medsam2_sam2):
            logger.debug(
                "Evicting cached sam2 module from %s to use MedSAM2's copy.", mod_file
            )
            to_remove = [k for k in sys.modules if k == "sam2" or k.startswith("sam2.")]
            for k in to_remove:
                del sys.modules[k]

            # Also reset Hydra if it was initialised by the old sam2 package
            try:
                from hydra.core.global_hydra import GlobalHydra
                if GlobalHydra.instance().is_initialized():
                    GlobalHydra.instance().clear()
            except Exception:
                pass

    # Import sam2 — triggers sam2/__init__.py → hydra.initialize_config_module
    import sam2  # noqa: F401


def _prepare_imgs(
    volume: np.ndarray,
    img_size: int,
    img_mean: tuple,
    img_std: tuple,
    device: str,
) -> torch.Tensor:
    """Convert a (D, H, W) float32 [0,1] volume to a (D, 3, S, S) tensor.

    Steps
    -----
    1. Resize each slice to (img_size, img_size) via PIL (nearest to LANCZOS).
    2. Stack to 3 channels (grayscale → RGB).
    3. Normalise with ImageNet mean/std.
    4. Move to *device*.
    """
    from PIL import Image as _PIL_Image

    D, H, W = volume.shape
    out = np.zeros((D, 3, img_size, img_size), dtype=np.float32)

    for i in range(D):
        sl_u8 = (np.clip(volume[i], 0.0, 1.0) * 255).astype(np.uint8)
        pil = _PIL_Image.fromarray(sl_u8).convert("RGB")
        pil = pil.resize((img_size, img_size), _PIL_Image.LANCZOS)
        arr = np.array(pil, dtype=np.float32) / 255.0  # (S, S, 3)
        out[i] = arr.transpose(2, 0, 1)  # (3, S, S)

    tensor = torch.from_numpy(out)  # (D, 3, S, S)
    mean = torch.tensor(img_mean, dtype=torch.float32)[:, None, None]
    std  = torch.tensor(img_std,  dtype=torch.float32)[:, None, None]
    tensor = (tensor - mean) / std

    return tensor.to(device)


def _add_prompts(predictor: Any, state: Any, prompts: List[Prompt]) -> None:
    """Add all box prompts to a fresh inference state."""
    for p in prompts:
        if p.box is None:
            continue
        predictor.add_new_points_or_box(
            inference_state=state,
            frame_idx=p.slice_idx,
            obj_id=1,
            box=np.array(p.box, dtype=np.float32),
        )


def _extract_along_axis(
    volume: np.ndarray, axis: int
) -> tuple[np.ndarray, int, int]:
    """Return (slices, H, W) where slices is (n, H, W) extracted along *axis*.

    volume shape convention: (H, W, D)  (nifti_utils / NiftiReader convention).
    axis 0 → slice along first dim (H),  each slice is (W, D)
    axis 1 → slice along second dim (W), each slice is (H, D)
    axis 2 → slice along third dim (D),  each slice is (H, W)
    """
    vol = np.moveaxis(volume, axis, 0)   # (n_slices, dim1, dim2)
    n, h, w = vol.shape
    return vol, h, w


def _get_axis_slice(volume: np.ndarray, idx: int, axis: int) -> np.ndarray:
    if axis == 0:
        return volume[idx]
    elif axis == 1:
        return volume[:, idx, :]
    else:
        return volume[:, :, idx]


def _set_axis_slice(
    volume: np.ndarray, idx: int, mask: np.ndarray, axis: int
) -> None:
    if axis == 0:
        volume[idx] = mask
    elif axis == 1:
        volume[:, idx, :] = mask
    else:
        volume[:, :, idx] = mask


def _autocast_ctx(device: str):
    """Return an appropriate autocast context for the device."""
    if "cuda" in device and torch.cuda.is_available():
        return torch.autocast("cuda", dtype=torch.bfloat16)
    # CPU: use a no-op context manager
    import contextlib
    return contextlib.nullcontext()
