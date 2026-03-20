"""I/O utilities: NIfTI reading/writing, image output, preprocessing."""

# ── Backward-compatible re-exports ──────────────────────────────────────────
from .nifti_reader import NiftiReader, load_nifti, normalize_intensity
from .image_writer import (
    save_mask_nifti,
    save_overlay_png,
    save_overlay_grid,
    save_prompts_json,
    save_metrics_json,
)

# ── New nifti_utils public API ──────────────────────────────────────────────
from .nifti_utils import (
    load_nifti_with_meta,
    NiftiMeta,
    clip_percentile,
    window_intensity,
    minmax_normalize,
    zscore_normalize,
    get_slice,
    set_slice,
    num_slices,
    get_slice_uint8,
    get_slice_rgb,
    get_voxel_spacing,
    get_orientation_info,
    ensure_3d,
    maybe_reorient_to_canonical,
    compute_physical_volume,
    save_nifti,
)

__all__ = [
    # Reader
    "NiftiReader",
    "load_nifti",
    "load_nifti_with_meta",
    "NiftiMeta",
    # Normalization
    "normalize_intensity",
    "clip_percentile",
    "window_intensity",
    "minmax_normalize",
    "zscore_normalize",
    # Slice
    "get_slice",
    "set_slice",
    "num_slices",
    "get_slice_uint8",
    "get_slice_rgb",
    # Metadata / geometry
    "get_voxel_spacing",
    "get_orientation_info",
    "ensure_3d",
    "maybe_reorient_to_canonical",
    "compute_physical_volume",
    # Saving
    "save_nifti",
    "save_mask_nifti",
    # Image output
    "save_overlay_png",
    "save_overlay_grid",
    "save_prompts_json",
    "save_metrics_json",
]
