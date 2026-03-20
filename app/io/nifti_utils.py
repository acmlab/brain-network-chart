"""
Unified NIfTI utility layer for the MedSAM Agent project.

This module is the single source of truth for all NIfTI-related operations:
  - Loading volumes (.nii / .nii.gz)
  - Intensity normalization & preprocessing
  - Slice extraction and mutation
  - Metadata / geometry helpers
  - Saving volumes and masks

Higher-level wrappers (NiftiReader, image_writer) delegate to functions here.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  A.  NIfTI Loading
# ═══════════════════════════════════════════════════════════════════════════════


def load_nifti(
    path: Union[str, Path],
    reorient: bool = False,
) -> Tuple[np.ndarray, np.ndarray, Any]:
    """Load a NIfTI file and return ``(volume, affine, header)``.

    Parameters
    ----------
    path : str or Path
        Path to a ``.nii`` or ``.nii.gz`` file.
    reorient : bool
        If *True*, reorient to the closest canonical (RAS+) orientation.

    Returns
    -------
    volume : np.ndarray
        Voxel data as float32.  4-D volumes are collapsed to 3-D
        (first temporal frame).
    affine : np.ndarray, shape (4, 4)
    header : nibabel header object

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"NIfTI file not found: {path}")

    img = nib.load(str(path))

    if reorient:
        img = nib.as_closest_canonical(img)

    volume = img.get_fdata(dtype=np.float32)
    volume = ensure_3d(volume)

    return volume, img.affine.copy(), img.header


@dataclass
class NiftiMeta:
    """Rich metadata bundle returned by :func:`load_nifti_with_meta`."""

    volume: np.ndarray
    affine: np.ndarray
    header: Any
    spacing: Tuple[float, float, float]
    shape: Tuple[int, ...]
    dtype: np.dtype

    def __repr__(self) -> str:
        return (
            f"NiftiMeta(shape={self.shape}, spacing={self.spacing}, "
            f"dtype={self.dtype})"
        )


def load_nifti_with_meta(
    path: Union[str, Path],
    reorient: bool = False,
) -> NiftiMeta:
    """Load a NIfTI file and return a :class:`NiftiMeta` bundle.

    This is a convenience wrapper around :func:`load_nifti` that also
    extracts voxel spacing, shape, and dtype into a structured object.

    Parameters
    ----------
    path : str or Path
        Path to a ``.nii`` or ``.nii.gz`` file.
    reorient : bool
        If *True*, reorient to closest canonical (RAS+) orientation.

    Returns
    -------
    NiftiMeta
    """
    volume, affine, header = load_nifti(path, reorient=reorient)
    spacing = get_voxel_spacing(header)
    return NiftiMeta(
        volume=volume,
        affine=affine,
        header=header,
        spacing=spacing,
        shape=volume.shape,
        dtype=volume.dtype,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  B.  Intensity Normalization / Preprocessing
# ═══════════════════════════════════════════════════════════════════════════════


def normalize_intensity(
    volume: np.ndarray,
    method: str = "percentile",
    *,
    low: float = 1.0,
    high: float = 99.0,
    center: float = 40.0,
    width: float = 400.0,
    out_range: Tuple[float, float] = (0.0, 1.0),
) -> np.ndarray:
    """Normalize voxel intensities to ``[0, 1]`` (or *out_range*).

    Dispatches to the method-specific helpers below.

    Parameters
    ----------
    volume : np.ndarray
        Input array (any shape).
    method : str
        ``"percentile"`` — clip to [P_low, P_high] then scale.
        ``"window"``     — CT Hounsfield-unit window (center ± width/2).
        ``"minmax"``     — global min-max.
        ``"zscore"``     — zero mean, unit variance.
    low, high : float
        Percentiles for the ``"percentile"`` method.
    center, width : float
        For the ``"window"`` method (CT HU).
    out_range : tuple of float
        Desired output (min, max) after normalization.

    Returns
    -------
    np.ndarray, dtype float32
        Same shape as *volume*, values in *out_range*.
    """
    v = _sanitise_volume(volume)

    if method == "percentile":
        v = clip_percentile(v, low=low, high=high)
    elif method == "window":
        v = window_intensity(v, center=center, width=width)
    elif method == "minmax":
        v = minmax_normalize(v)
    elif method == "zscore":
        return zscore_normalize(v)       # z-score has its own range
    else:
        raise ValueError(f"Unknown normalization method: {method!r}")

    # At this point *v* is in [0, 1].  Rescale to *out_range*.
    lo, hi = out_range
    if (lo, hi) != (0.0, 1.0):
        v = v * (hi - lo) + lo

    return v.astype(np.float32)


def clip_percentile(
    volume: np.ndarray,
    low: float = 1.0,
    high: float = 99.0,
) -> np.ndarray:
    """Clip intensities to [P_low, P_high] percentiles and scale to [0, 1].

    Parameters
    ----------
    volume : np.ndarray
        Input array (any shape).
    low : float
        Lower percentile (0–100).
    high : float
        Upper percentile (0–100).

    Returns
    -------
    np.ndarray, dtype float32, values in [0, 1].
    """
    v = _sanitise_volume(volume)
    p_low = float(np.percentile(v, low))
    p_high = float(np.percentile(v, high))
    return _clip_and_scale(v, p_low, p_high)


def window_intensity(
    volume: np.ndarray,
    center: float,
    width: float,
) -> np.ndarray:
    """Apply a CT-style intensity window and scale to [0, 1].

    Parameters
    ----------
    volume : np.ndarray
        Input array.
    center : float
        Window centre (Hounsfield units or raw).
    width : float
        Window width.

    Returns
    -------
    np.ndarray, dtype float32, values in [0, 1].
    """
    v = _sanitise_volume(volume)
    lo = center - width / 2.0
    hi = center + width / 2.0
    return _clip_and_scale(v, lo, hi)


def minmax_normalize(volume: np.ndarray) -> np.ndarray:
    """Global min-max normalization to [0, 1].

    Parameters
    ----------
    volume : np.ndarray

    Returns
    -------
    np.ndarray, dtype float32, values in [0, 1].
    """
    v = _sanitise_volume(volume)
    lo = float(v.min())
    hi = float(v.max())
    return _clip_and_scale(v, lo, hi)


def zscore_normalize(
    volume: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Z-score normalization (zero mean, unit variance).

    Parameters
    ----------
    volume : np.ndarray
        Input array.
    mask : np.ndarray or None
        If provided, compute mean/std only inside the mask.

    Returns
    -------
    np.ndarray, dtype float32.  Values are *not* clamped to [0, 1].
    """
    v = _sanitise_volume(volume)
    if mask is not None:
        vals = v[mask.astype(bool)]
    else:
        vals = v.ravel()

    mu = float(vals.mean())
    sigma = float(vals.std())
    if sigma < 1e-8:
        logger.warning("zscore_normalize: near-zero std — returning zeros.")
        return np.zeros_like(v, dtype=np.float32)
    return ((v - mu) / sigma).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
#  C.  Slice Extraction / Mutation
# ═══════════════════════════════════════════════════════════════════════════════


def get_slice(
    volume: np.ndarray,
    idx: int,
    axis: int = 0,
) -> np.ndarray:
    """Extract a 2-D slice from a 3-D volume.

    Parameters
    ----------
    volume : np.ndarray, shape (..., D)
        3-D (or higher) volume.
    idx : int
        Slice index along *axis*.  Clamped to valid range.
    axis : int
        0 → dim-0 (axial), 1 → dim-1 (coronal), 2 → dim-2 (sagittal).

    Returns
    -------
    np.ndarray, 2-D view into *volume*.
    """
    if axis not in (0, 1, 2):
        raise ValueError(f"axis must be 0, 1, or 2; got {axis}")

    idx = _clamp_idx(idx, volume.shape[axis])

    if axis == 0:
        return volume[idx, :, :]
    elif axis == 1:
        return volume[:, idx, :]
    else:
        return volume[:, :, idx]


def set_slice(
    volume: np.ndarray,
    idx: int,
    slice_data: np.ndarray,
    axis: int = 0,
) -> None:
    """Write a 2-D array into a 3-D volume at position *idx* along *axis*.

    Parameters
    ----------
    volume : np.ndarray
        3-D volume (modified in-place).
    idx : int
        Slice index along *axis*.
    slice_data : np.ndarray
        2-D array matching the expected slice shape.
    axis : int
        0, 1, or 2.
    """
    if axis == 0:
        volume[idx, :, :] = slice_data
    elif axis == 1:
        volume[:, idx, :] = slice_data
    elif axis == 2:
        volume[:, :, idx] = slice_data
    else:
        raise ValueError(f"axis must be 0, 1, or 2; got {axis}")


def num_slices(volume: np.ndarray, axis: int = 0) -> int:
    """Return the number of slices along *axis*.

    Parameters
    ----------
    volume : np.ndarray
    axis : int

    Returns
    -------
    int
    """
    return volume.shape[axis]


def get_slice_uint8(
    volume: np.ndarray,
    idx: int,
    axis: int = 0,
    normalized: bool = True,
) -> np.ndarray:
    """Extract a 2-D slice and convert to uint8 [0, 255].

    Parameters
    ----------
    volume : np.ndarray
        3-D volume.  If *normalized* is True, values should be in [0, 1].
    idx : int
        Slice index.
    axis : int
    normalized : bool
        If True, treat values as [0, 1] and scale by 255.
        Otherwise, apply per-slice min-max scaling first.

    Returns
    -------
    np.ndarray, dtype uint8, shape (H, W).
    """
    sl = get_slice(volume, idx, axis=axis)

    if normalized:
        return (np.clip(sl, 0.0, 1.0) * 255.0).astype(np.uint8)

    lo, hi = float(sl.min()), float(sl.max())
    if hi > lo:
        return ((sl - lo) / (hi - lo) * 255.0).astype(np.uint8)
    return np.zeros_like(sl, dtype=np.uint8)


def get_slice_rgb(
    volume: np.ndarray,
    idx: int,
    axis: int = 0,
    cmap: str = "gray",
) -> np.ndarray:
    """Extract a 2-D slice as an RGB uint8 array ``(H, W, 3)``.

    Parameters
    ----------
    volume : np.ndarray
        3-D float32 volume, values in [0, 1].
    idx : int
    axis : int
    cmap : str
        Matplotlib colour map name.

    Returns
    -------
    np.ndarray, dtype uint8, shape (H, W, 3).
    """
    import matplotlib.pyplot as plt

    sl = get_slice(volume, idx, axis=axis).astype(np.float64)
    sl = np.clip(sl, 0.0, 1.0)
    colormap = plt.get_cmap(cmap)
    rgba = (colormap(sl) * 255).astype(np.uint8)   # (H, W, 4)
    return rgba[..., :3]


# ═══════════════════════════════════════════════════════════════════════════════
#  D.  Metadata / Geometry
# ═══════════════════════════════════════════════════════════════════════════════


def get_voxel_spacing(header: Any) -> Tuple[float, float, float]:
    """Extract voxel spacing ``(dx, dy, dz)`` in mm from a nibabel header.

    Parameters
    ----------
    header : nibabel header object

    Returns
    -------
    tuple of float
        Voxel size along each spatial dimension.  Falls back to
        ``(1.0, 1.0, 1.0)`` if the header lacks zoom information.
    """
    try:
        zooms = header.get_zooms()
        if len(zooms) >= 3:
            return (float(zooms[0]), float(zooms[1]), float(zooms[2]))
    except Exception:
        pass
    return (1.0, 1.0, 1.0)


def get_orientation_info(
    img_or_header: Any,
) -> Dict[str, Any]:
    """Return orientation metadata (axis codes, affine) for a NIfTI image.

    Parameters
    ----------
    img_or_header : nib.Nifti1Image or nibabel header

    Returns
    -------
    dict with keys ``"axcodes"``, ``"ornt"``, ``"affine"``.
    """
    if isinstance(img_or_header, nib.Nifti1Image):
        affine = img_or_header.affine
    elif hasattr(img_or_header, "get_best_affine"):
        affine = img_or_header.get_best_affine()
    else:
        return {"axcodes": ("?", "?", "?"), "ornt": None, "affine": None}

    ornt = nib.orientations.io_orientation(affine)
    axcodes = nib.orientations.ornt2axcodes(ornt)
    return {
        "axcodes": tuple(axcodes),
        "ornt": ornt,
        "affine": affine,
    }


def ensure_3d(volume: np.ndarray) -> np.ndarray:
    """Guarantee a 3-D array.  Collapse 4-D to 3-D (first temporal frame).

    Parameters
    ----------
    volume : np.ndarray
        Array with ndim in {2, 3, 4}.

    Returns
    -------
    np.ndarray with ndim == 3.

    Raises
    ------
    ValueError
        If *volume* has fewer than 2 or more than 4 dimensions.
    """
    if volume.ndim == 3:
        return volume
    if volume.ndim == 4:
        return volume[..., 0]
    if volume.ndim == 2:
        return volume[:, :, np.newaxis]
    raise ValueError(
        f"Expected 2-D, 3-D, or 4-D volume, got ndim={volume.ndim}"
    )


def maybe_reorient_to_canonical(
    path_or_img: Union[str, Path, nib.Nifti1Image],
) -> nib.Nifti1Image:
    """Load (if a path) and reorient a NIfTI image to RAS+ canonical.

    Parameters
    ----------
    path_or_img : str, Path, or nib.Nifti1Image

    Returns
    -------
    nib.Nifti1Image in canonical (RAS+) orientation.
    """
    if isinstance(path_or_img, (str, Path)):
        img = nib.load(str(path_or_img))
    else:
        img = path_or_img
    return nib.as_closest_canonical(img)


def compute_physical_volume(
    mask: np.ndarray,
    spacing: Tuple[float, float, float],
) -> float:
    """Compute the physical volume (mm³) of foreground voxels.

    Parameters
    ----------
    mask : np.ndarray
        Binary mask (nonzero = foreground).
    spacing : tuple of float
        Voxel size ``(dx, dy, dz)`` in mm.

    Returns
    -------
    float — volume in mm³.
    """
    voxel_vol = float(spacing[0] * spacing[1] * spacing[2])
    return float((mask > 0).sum()) * voxel_vol


# ═══════════════════════════════════════════════════════════════════════════════
#  E.  Saving Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def save_nifti(
    volume: np.ndarray,
    out_path: Union[str, Path],
    affine: Optional[np.ndarray] = None,
    header: Any = None,
    dtype: Optional[np.dtype] = None,
) -> Path:
    """Save an arbitrary array as a NIfTI file.

    Parameters
    ----------
    volume : np.ndarray
        Data to write.
    out_path : str or Path
        Destination.  Should end in ``.nii.gz`` or ``.nii``.
    affine : np.ndarray or None
        4×4 affine matrix.  Defaults to identity.
    header : nibabel header or None
        Optional reference header (preserves spacing, orientation, …).
    dtype : np.dtype or None
        If given, cast *volume* before saving.

    Returns
    -------
    Path to the written file.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if dtype is not None:
        volume = volume.astype(dtype)
    if affine is None:
        affine = np.eye(4)

    if header is not None:
        nii = nib.Nifti1Image(volume, affine=affine, header=header)
    else:
        nii = nib.Nifti1Image(volume, affine=affine)

    nib.save(nii, str(out_path))
    return out_path


def save_mask_nifti(
    mask: np.ndarray,
    out_path: Union[str, Path],
    reference_affine: Optional[np.ndarray] = None,
    reference_header: Any = None,
) -> Path:
    """Save a binary (or multi-label) 3-D mask as ``.nii.gz``.

    The mask is cast to uint8 and the NIfTI header data-type is forced to
    uint8.  Geometry is preserved via *reference_affine* / *reference_header*.

    Parameters
    ----------
    mask : np.ndarray
        Integer array of shape (H, W, D).
    out_path : str or Path
        Destination path (should end in .nii.gz).
    reference_affine : np.ndarray or None
        Affine from the source volume.
    reference_header : nibabel header or None
        Header from the source volume.

    Returns
    -------
    Path to the saved file.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mask_u8 = mask.astype(np.uint8)
    aff = reference_affine if reference_affine is not None else np.eye(4)

    if reference_header is not None:
        nii = nib.Nifti1Image(mask_u8, affine=aff, header=reference_header)
    else:
        nii = nib.Nifti1Image(mask_u8, affine=aff)

    nii.header.set_data_dtype(np.uint8)
    nib.save(nii, str(out_path))
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
#  Private Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _sanitise_volume(volume: np.ndarray) -> np.ndarray:
    """Copy, cast to float32, and replace NaN/Inf with finite values."""
    v = volume.astype(np.float32, copy=True)
    nan_count = int(np.isnan(v).sum())
    inf_count = int(np.isinf(v).sum())
    if nan_count > 0 or inf_count > 0:
        logger.warning(
            f"Volume contains {nan_count} NaN and {inf_count} Inf values "
            "— replacing with 0."
        )
        np.nan_to_num(v, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return v


def _clip_and_scale(
    volume: np.ndarray,
    lo: float,
    hi: float,
) -> np.ndarray:
    """Clip to [lo, hi] and linearly scale to [0, 1].

    Returns zeros for flat (lo == hi) volumes.
    """
    if hi <= lo:
        return np.zeros_like(volume, dtype=np.float32)
    v = np.clip(volume, lo, hi)
    return ((v - lo) / (hi - lo)).astype(np.float32)


def _clamp_idx(idx: int, n: int) -> int:
    """Clamp *idx* to [0, n-1]."""
    return max(0, min(idx, n - 1))
