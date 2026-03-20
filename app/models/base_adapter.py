"""
Abstract base class for segmentation backends.

All adapters (MedSAM, SAM, future models) must implement this interface so
that the agent layer remains model-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ─── Data structures ─────────────────────────────────────────────────────────


@dataclass
class Prompt:
    """A single user-provided prompt for one slice.

    Attributes
    ----------
    slice_idx:
        Index of the slice (in the volume's primary axis).
    axis:
        Axis along which the slice is taken (0=axial, 1=coronal, 2=sagittal).
    prompt_type:
        "box" | "point" | "scribble"
    box:
        Bounding box [x1, y1, x2, y2] in *pixel* coordinates of the slice.
        Required when prompt_type == "box".
    points:
        List of (x, y, label) tuples.  label=1 foreground, 0 background.
        Used for prompt_type == "point".
    scribble_mask:
        Optional binary 2D array for scribble prompts.
    meta:
        Extra metadata (organ name, timestamp, confidence …).
    """

    slice_idx: int
    axis: int = 0
    prompt_type: str = "box"
    box: Optional[List[float]] = None          # [x1, y1, x2, y2]
    points: Optional[List[Tuple[float, float, int]]] = None  # [(x, y, label), ...]
    scribble_mask: Optional[np.ndarray] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-safe dict (excludes ndarray)."""
        d: Dict[str, Any] = {
            "slice_idx": self.slice_idx,
            "axis": self.axis,
            "prompt_type": self.prompt_type,
            "meta": self.meta,
        }
        if self.box is not None:
            d["box"] = self.box
        if self.points is not None:
            d["points"] = self.points
        return d


@dataclass
class SegResult:
    """Result returned by a segmentation backend for one slice.

    Attributes
    ----------
    slice_idx:
        Slice index in the volume.
    mask:
        Binary uint8 2D array (H, W).
    logits:
        Optional raw float logits (H, W).
    confidence:
        Optional scalar confidence in [0, 1].
    meta:
        Extra information from the model.
    """

    slice_idx: int
    mask: np.ndarray         # uint8 (H, W)
    logits: Optional[np.ndarray] = None
    confidence: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


# ─── Abstract adapter ────────────────────────────────────────────────────────


class BaseSegAdapter(ABC):
    """Interface every segmentation backend must implement."""

    def __init__(self, device: str = "cuda", **kwargs: Any):
        self.device = device
        self._loaded: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    @abstractmethod
    def load_model(self, checkpoint: str, **kwargs: Any) -> None:
        """Load model weights from *checkpoint* onto *self.device*."""
        ...

    def is_loaded(self) -> bool:
        return self._loaded

    # ── Core inference ───────────────────────────────────────────────────────

    @abstractmethod
    def predict_slice(
        self,
        image_slice: np.ndarray,
        prompt: Prompt,
    ) -> SegResult:
        """Run inference on a single 2D slice.

        Parameters
        ----------
        image_slice:
            Float32 array in [0, 1], shape (H, W).
        prompt:
            User-provided prompt for this slice.

        Returns
        -------
        SegResult with mask, optional logits, confidence.
        """
        ...

    def predict_volume(
        self,
        image_volume: np.ndarray,
        prompts: List[Prompt],
        axis: int = 0,
    ) -> np.ndarray:
        """Run inference on all prompted slices and return full 3D mask.

        Default implementation delegates to predict_slice for each prompt.
        Subclasses may override with a more efficient batch approach.

        Parameters
        ----------
        image_volume:
            Float32 normalized volume (H, W, D).
        prompts:
            List of Prompt objects (may span multiple slices).
        axis:
            Axis along which slices are extracted.

        Returns
        -------
        Partial mask (H, W, D) — only prompted slices are filled.
        Full propagation is handled by the Orchestrator.
        """
        shape = list(image_volume.shape)
        mask_volume = np.zeros(shape, dtype=np.uint8)

        for prompt in prompts:
            idx = prompt.slice_idx
            if axis == 0:
                sl = image_volume[idx, :, :]
            elif axis == 1:
                sl = image_volume[:, idx, :]
            else:
                sl = image_volume[:, :, idx]

            result = self.predict_slice(sl, prompt)

            if axis == 0:
                mask_volume[idx, :, :] = result.mask
            elif axis == 1:
                mask_volume[:, idx, :] = result.mask
            else:
                mask_volume[:, :, idx] = result.mask

        return mask_volume

    def refine_with_prompts(
        self,
        image_slice: np.ndarray,
        existing_mask: np.ndarray,
        new_prompt: Prompt,
    ) -> SegResult:
        """Refine an existing segmentation using an additional prompt.

        Default: ignore existing mask and re-run predict_slice.
        Adapters that support mask-conditioned refinement can override.
        """
        return self.predict_slice(image_slice, new_prompt)

    # ── Utility ──────────────────────────────────────────────────────────────

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError(
                f"{self.__class__.__name__} model not loaded. "
                "Call load_model() first."
            )
