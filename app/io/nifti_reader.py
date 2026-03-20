"""
NIfTI volume reader — high-level OOP wrapper.

Delegates all low-level operations to :mod:`app.io.nifti_utils`.
Caches the loaded volume and its normalized version so that repeated
slice extraction is fast.

Public free functions ``load_nifti`` and ``normalize_intensity`` are
re-exported from ``nifti_utils`` for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

# ── Re-exports from the canonical location (backward compatibility) ──────────
from .nifti_utils import (
    load_nifti,
    normalize_intensity,
)
from . import nifti_utils as _nu


# ─── NiftiReader class ───────────────────────────────────────────────────────


class NiftiReader:
    """High-level reader for 3D NIfTI volumes.

    Caches the loaded volume and its normalized version so that repeated
    slice extraction is fast.

    Example
    -------
    >>> reader = NiftiReader("path/to/volume.nii.gz")
    >>> reader.load()
    >>> slice_img = reader.get_slice(axis=0, idx=50, normalized=True)
    """

    def __init__(
        self,
        path: str | Path,
        norm_method: str = "percentile",
        norm_kwargs: Optional[Dict[str, Any]] = None,
        reorient: bool = False,
    ):
        self.path = Path(path)
        self.norm_method = norm_method
        self.norm_kwargs: Dict[str, Any] = norm_kwargs or {}
        self.reorient = reorient

        self._volume: Optional[np.ndarray] = None
        self._volume_norm: Optional[np.ndarray] = None
        self._affine: Optional[np.ndarray] = None
        self._header: Any = None
        self._loaded: bool = False

    # ── Public API ───────────────────────────────────────────────────────────

    def load(self) -> "NiftiReader":
        """Load volume from disk and cache normalized copy. Returns self."""
        raw, self._affine, self._header = _nu.load_nifti(
            self.path, reorient=self.reorient
        )
        self._volume = raw
        self._volume_norm = _nu.normalize_intensity(
            raw, method=self.norm_method, **self.norm_kwargs
        )
        self._loaded = True
        return self

    @property
    def volume(self) -> np.ndarray:
        """Raw (unnormalized) volume array, shape (H, W, D)."""
        self._require_loaded()
        return self._volume  # type: ignore[return-value]

    @property
    def volume_norm(self) -> np.ndarray:
        """Normalized volume array, shape (H, W, D)."""
        self._require_loaded()
        return self._volume_norm  # type: ignore[return-value]

    @property
    def affine(self) -> np.ndarray:
        self._require_loaded()
        return self._affine  # type: ignore[return-value]

    @property
    def header(self) -> Any:
        self._require_loaded()
        return self._header

    @property
    def shape(self) -> Tuple[int, ...]:
        self._require_loaded()
        return self._volume.shape  # type: ignore[union-attr]

    def num_slices(self, axis: int = 0) -> int:
        """Return number of slices along the given axis."""
        self._require_loaded()
        return _nu.num_slices(self._volume, axis)  # type: ignore[arg-type]

    def get_slice(
        self,
        idx: int,
        axis: int = 0,
        normalized: bool = True,
        as_uint8: bool = False,
    ) -> np.ndarray:
        """Extract a 2D slice.

        Parameters
        ----------
        idx:
            Slice index along *axis*.
        axis:
            0 → axial (H×W), 1 → coronal, 2 → sagittal.
        normalized:
            Return from normalized volume if True.
        as_uint8:
            Convert to uint8 [0, 255] for display.

        Returns
        -------
        np.ndarray, shape (H, W), dtype float32 or uint8.
        """
        self._require_loaded()
        vol = self._volume_norm if normalized else self._volume
        assert vol is not None

        if as_uint8:
            return _nu.get_slice_uint8(vol, idx, axis=axis, normalized=normalized)

        return _nu.get_slice(vol, idx, axis=axis)

    def get_slice_rgb(
        self, idx: int, axis: int = 0, cmap: str = "gray"
    ) -> np.ndarray:
        """Return a 2D slice as an RGB uint8 array (H, W, 3)."""
        self._require_loaded()
        return _nu.get_slice_rgb(self._volume_norm, idx, axis=axis, cmap=cmap)  # type: ignore[arg-type]

    def voxel_spacing(self) -> Tuple[float, float, float]:
        """Return voxel spacing (dx, dy, dz) in mm from header."""
        self._require_loaded()
        return _nu.get_voxel_spacing(self._header)

    # ── Private ──────────────────────────────────────────────────────────────

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError(
                "Volume not loaded. Call NiftiReader.load() first."
            )
