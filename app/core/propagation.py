"""
3D mask propagation: extend segmentations from prompted slices to the full volume.

Three strategies are implemented:

1. "sam_guided" (default, recommended)
   For each unprompted slice, derive a bounding-box prompt from the nearest
   segmented slice's mask, then run the model.  This gives the model context
   for each slice individually and handles anatomical drift better than
   interpolation alone.

2. "interpolate"
   Binary morphological interpolation between segmented slices using
   signed-distance-field linear interpolation, then threshold.  Fast, no
   model calls, but can produce artifacts in complex anatomy.

3. "nearest"
   Simply copy the mask from the nearest prompted slice.  Useful as a
   dead-simple baseline or when the model is unavailable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import numpy as np
from scipy.ndimage import distance_transform_edt

from ..io import nifti_utils as _nu

if TYPE_CHECKING:
    from ..models.base_adapter import BaseSegAdapter
    from ..agent.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class Propagator:
    """Propagates segmentation masks from seed slices to the full volume.

    Parameters
    ----------
    strategy:
        "sam_guided" | "interpolate" | "nearest"
    adapter:
        Segmentation model adapter (needed for sam_guided).
    bbox_expand_ratio:
        When deriving bboxes from masks for sam_guided, expand by this fraction.
    """

    def __init__(
        self,
        strategy: str = "sam_guided",
        adapter: Optional["BaseSegAdapter"] = None,
        bbox_expand_ratio: float = 0.05,
    ):
        self.strategy = strategy
        self.adapter = adapter
        self.bbox_expand_ratio = bbox_expand_ratio

    def propagate(
        self,
        image_volume: np.ndarray,
        partial_mask: np.ndarray,
        prompted_slices: List[int],
        axis: int,
        n_total: int,
        prompt_manager: Optional["PromptManager"] = None,
    ) -> np.ndarray:
        """Fill in unprompted slices.

        Parameters
        ----------
        image_volume:
            Normalized float32 volume (H, W, D).
        partial_mask:
            Binary mask with prompted slices already filled; zeros elsewhere.
        prompted_slices:
            Sorted list of slice indices that are already segmented.
        axis:
            Primary axis.
        n_total:
            Total slices along *axis*.
        prompt_manager:
            PromptManager (used in sam_guided for prompt records).

        Returns
        -------
        Full binary mask (H, W, D) as uint8.
        """
        if not prompted_slices:
            logger.warning("No prompted slices — returning empty mask.")
            return partial_mask

        if self.strategy == "sam_guided":
            return self._sam_guided(
                image_volume, partial_mask, prompted_slices, axis, n_total
            )
        elif self.strategy == "interpolate":
            return self._interpolate(partial_mask, prompted_slices, axis, n_total)
        elif self.strategy == "nearest":
            return self._nearest(partial_mask, prompted_slices, axis, n_total)
        else:
            raise ValueError(f"Unknown propagation strategy: {self.strategy!r}")

    # ── Strategy implementations ──────────────────────────────────────────────

    def _sam_guided(
        self,
        image_volume: np.ndarray,
        partial_mask: np.ndarray,
        prompted_slices: List[int],
        axis: int,
        n_total: int,
    ) -> np.ndarray:
        """For each unprompted slice, infer using bbox derived from nearest seed."""
        if self.adapter is None or not self.adapter.is_loaded():
            logger.warning(
                "SAM-guided propagation requires a loaded adapter. "
                "Falling back to interpolation."
            )
            return self._interpolate(partial_mask, prompted_slices, axis, n_total)

        from ..models.base_adapter import Prompt

        result = partial_mask.copy()
        prompted_set = set(prompted_slices)

        for idx in range(n_total):
            if idx in prompted_set:
                continue

            # Find nearest prompted slice
            nearest = min(prompted_slices, key=lambda s: abs(s - idx))
            ref_mask = _nu.get_slice(result, nearest, axis)

            if not ref_mask.any():
                continue  # Reference mask is empty — skip

            # Derive bbox from reference mask
            box = _mask_to_bbox(ref_mask, expand=self.bbox_expand_ratio)
            if box is None:
                continue

            img_slice = _nu.get_slice(image_volume, idx, axis)
            prompt = Prompt(
                slice_idx=idx,
                axis=axis,
                prompt_type="box",
                box=box,
                meta={"source": "propagation", "ref_slice": nearest},
            )
            try:
                seg_result = self.adapter.predict_slice(img_slice, prompt)
                _nu.set_slice(result, idx, seg_result.mask, axis)
            except Exception as exc:
                logger.warning(f"SAM propagation failed at slice {idx}: {exc}")

        logger.info(f"SAM-guided propagation complete: {n_total} slices processed.")
        return result

    def _interpolate(
        self,
        partial_mask: np.ndarray,
        prompted_slices: List[int],
        axis: int,
        n_total: int,
    ) -> np.ndarray:
        """Signed-distance-field interpolation between prompted slices."""
        result = partial_mask.copy()
        prompted_sorted = sorted(prompted_slices)

        def _sdf(binary_mask: np.ndarray) -> np.ndarray:
            """Signed distance field: positive inside, negative outside."""
            pos = distance_transform_edt(binary_mask)
            neg = distance_transform_edt(1 - binary_mask)
            return pos - neg

        # Interpolate between each consecutive pair of prompted slices
        for i in range(len(prompted_sorted) - 1):
            s0 = prompted_sorted[i]
            s1 = prompted_sorted[i + 1]
            mask0 = _nu.get_slice(partial_mask, s0, axis).astype(np.float32)
            mask1 = _nu.get_slice(partial_mask, s1, axis).astype(np.float32)
            sdf0 = _sdf(mask0)
            sdf1 = _sdf(mask1)

            for j in range(s0 + 1, s1):
                t = (j - s0) / (s1 - s0)
                interp_sdf = (1 - t) * sdf0 + t * sdf1
                interp_mask = (interp_sdf > 0).astype(np.uint8)
                _nu.set_slice(result, j, interp_mask, axis)

        # Propagate forward from last prompted slice
        last = prompted_sorted[-1]
        last_mask = _nu.get_slice(partial_mask, last, axis)
        for j in range(last + 1, n_total):
            _nu.set_slice(result, j, last_mask.copy(), axis)

        # Propagate backward from first prompted slice
        first = prompted_sorted[0]
        first_mask = _nu.get_slice(partial_mask, first, axis)
        for j in range(0, first):
            _nu.set_slice(result, j, first_mask.copy(), axis)

        logger.info("SDF interpolation propagation complete.")
        return result

    def _nearest(
        self,
        partial_mask: np.ndarray,
        prompted_slices: List[int],
        axis: int,
        n_total: int,
    ) -> np.ndarray:
        """Copy the nearest seed slice mask to every unprompted slice."""
        result = partial_mask.copy()
        prompted_set = set(prompted_slices)

        for idx in range(n_total):
            if idx in prompted_set:
                continue
            nearest = min(prompted_slices, key=lambda s: abs(s - idx))
            ref_mask = _nu.get_slice(partial_mask, nearest, axis)
            _nu.set_slice(result, idx, ref_mask.copy(), axis)

        return result


# ─── Private helpers ──────────────────────────────────────────────────────────


def _mask_to_bbox(
    mask: np.ndarray,
    expand: float = 0.05,
) -> Optional[List[float]]:
    """Compute bounding box [x1, y1, x2, y2] of a binary mask.

    Returns None if the mask is empty.
    """
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any():
        return None

    r_min, r_max = np.where(rows)[0][[0, -1]]
    c_min, c_max = np.where(cols)[0][[0, -1]]

    H, W = mask.shape
    pad_r = max(1, int((r_max - r_min) * expand))
    pad_c = max(1, int((c_max - c_min) * expand))

    x1 = max(0, float(c_min - pad_c))
    y1 = max(0, float(r_min - pad_r))
    x2 = min(W - 1, float(c_max + pad_c))
    y2 = min(H - 1, float(r_max + pad_r))

    return [x1, y1, x2, y2]
