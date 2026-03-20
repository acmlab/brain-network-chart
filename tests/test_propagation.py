"""Tests for 3D mask propagation strategies."""

import numpy as np
import pytest

from app.core.propagation import Propagator, _mask_to_bbox


# ─── Helper ───────────────────────────────────────────────────────────────────


def make_partial_mask(shape, axis, seed_slices, rect):
    """Create a partial mask with rectangles on seed slices."""
    mask = np.zeros(shape, dtype=np.uint8)
    y1, y2, x1, x2 = rect
    for s in seed_slices:
        if axis == 0:
            mask[s, y1:y2, x1:x2] = 1
        elif axis == 1:
            mask[y1:y2, s, x1:x2] = 1
        else:
            mask[y1:y2, x1:x2, s] = 1
    return mask


# ─── _mask_to_bbox ────────────────────────────────────────────────────────────


def test_mask_to_bbox_basic():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:60, 30:70] = 1
    bbox = _mask_to_bbox(mask, expand=0.0)
    assert bbox is not None
    x1, y1, x2, y2 = bbox
    assert y1 <= 20 and y2 >= 59
    assert x1 <= 30 and x2 >= 69


def test_mask_to_bbox_empty():
    mask = np.zeros((100, 100), dtype=np.uint8)
    assert _mask_to_bbox(mask) is None


# ─── Nearest propagation ─────────────────────────────────────────────────────


def test_nearest_propagation():
    shape = (50, 64, 64)
    axis = 0
    seed_slices = [10, 40]
    partial = make_partial_mask(shape, axis, seed_slices, (20, 44, 20, 44))

    prop = Propagator(strategy="nearest")
    result = prop.propagate(
        image_volume=np.zeros(shape, dtype=np.float32),
        partial_mask=partial,
        prompted_slices=seed_slices,
        axis=axis,
        n_total=shape[0],
    )

    assert result.shape == shape
    # All slices should now be non-empty (copied from nearest seed)
    for i in range(shape[0]):
        assert result[i].any(), f"Slice {i} is empty after nearest propagation"


# ─── Interpolation propagation ────────────────────────────────────────────────


def test_interpolate_propagation():
    shape = (30, 64, 64)
    axis = 0
    seed_slices = [5, 25]
    partial = make_partial_mask(shape, axis, seed_slices, (15, 50, 15, 50))

    prop = Propagator(strategy="interpolate")
    result = prop.propagate(
        image_volume=np.zeros(shape, dtype=np.float32),
        partial_mask=partial,
        prompted_slices=seed_slices,
        axis=axis,
        n_total=shape[0],
    )

    assert result.shape == shape
    # Mid slice should have some foreground from interpolation
    mid = (seed_slices[0] + seed_slices[1]) // 2
    assert result[mid].any(), "Mid slice should be non-empty after interpolation"


def test_interpolate_single_seed():
    """With a single seed, nearest-copy is used for propagation."""
    shape = (20, 32, 32)
    axis = 0
    seed_slices = [10]
    partial = make_partial_mask(shape, axis, seed_slices, (8, 24, 8, 24))

    prop = Propagator(strategy="interpolate")
    result = prop.propagate(
        image_volume=np.zeros(shape, dtype=np.float32),
        partial_mask=partial,
        prompted_slices=seed_slices,
        axis=axis,
        n_total=shape[0],
    )
    assert result.shape == shape
    # Should propagate to both directions
    assert result[0].any()
    assert result[-1].any()


# ─── Mock adapter propagation ─────────────────────────────────────────────────


def test_sam_guided_falls_back_without_adapter():
    """Without adapter, sam_guided should fall back to interpolation."""
    shape = (20, 32, 32)
    axis = 0
    seed_slices = [5, 15]
    partial = make_partial_mask(shape, axis, seed_slices, (8, 24, 8, 24))

    prop = Propagator(strategy="sam_guided", adapter=None)
    result = prop.propagate(
        image_volume=np.zeros(shape, dtype=np.float32),
        partial_mask=partial,
        prompted_slices=seed_slices,
        axis=axis,
        n_total=shape[0],
    )
    assert result.shape == shape
