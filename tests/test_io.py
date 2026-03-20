"""Tests for NIfTI I/O utilities."""

import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.io.nifti_reader import NiftiReader, load_nifti, normalize_intensity
from app.io.image_writer import save_mask_nifti, save_overlay_png, save_prompts_json


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_nifti(tmp_path) -> Path:
    """Create a tiny synthetic NIfTI file for testing."""
    vol = np.random.default_rng(0).normal(100, 30, (32, 32, 20)).astype(np.float32)
    affine = np.eye(4)
    nii = nib.Nifti1Image(vol, affine)
    path = tmp_path / "test_volume.nii.gz"
    nib.save(nii, str(path))
    return path


# ─── load_nifti ────────────────────────────────────────────────────────────────


def test_load_nifti_basic(tmp_nifti):
    vol, affine, header = load_nifti(tmp_nifti)
    assert vol.ndim == 3
    assert vol.shape == (32, 32, 20)
    assert vol.dtype == np.float32
    assert affine.shape == (4, 4)


def test_load_nifti_not_found():
    with pytest.raises(FileNotFoundError):
        load_nifti("/nonexistent/path.nii.gz")


def test_load_nifti_4d(tmp_path):
    """4D volumes should be reduced to 3D (first frame)."""
    vol_4d = np.ones((16, 16, 10, 3), dtype=np.float32)
    nii = nib.Nifti1Image(vol_4d, np.eye(4))
    path = tmp_path / "vol4d.nii.gz"
    nib.save(nii, str(path))
    vol, _, _ = load_nifti(path)
    assert vol.ndim == 3
    assert vol.shape == (16, 16, 10)


# ─── normalize_intensity ───────────────────────────────────────────────────────


def test_normalize_percentile():
    vol = np.arange(100, dtype=np.float32).reshape(10, 10, 1)
    out = normalize_intensity(vol, method="percentile", low=0, high=100)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


def test_normalize_window():
    vol = np.array([[[0.0], [100.0], [400.0]]], dtype=np.float32)
    out = normalize_intensity(vol, method="window", center=100, width=200)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


def test_normalize_flat_volume():
    """Flat volume should return zeros, not NaN."""
    vol = np.ones((5, 5, 5), dtype=np.float32) * 42.0
    out = normalize_intensity(vol, method="percentile")
    assert np.all(out == 0.0)


# ─── NiftiReader ──────────────────────────────────────────────────────────────


def test_reader_basic(tmp_nifti):
    reader = NiftiReader(tmp_nifti).load()
    assert reader.shape == (32, 32, 20)
    assert reader.num_slices(axis=0) == 32
    assert reader.num_slices(axis=2) == 20


def test_reader_get_slice(tmp_nifti):
    reader = NiftiReader(tmp_nifti).load()
    sl = reader.get_slice(5, axis=0, normalized=True)
    assert sl.shape == (32, 20)
    assert sl.min() >= 0.0
    assert sl.max() <= 1.0


def test_reader_get_slice_uint8(tmp_nifti):
    reader = NiftiReader(tmp_nifti).load()
    sl = reader.get_slice(5, axis=0, as_uint8=True)
    assert sl.dtype == np.uint8


def test_reader_get_slice_rgb(tmp_nifti):
    reader = NiftiReader(tmp_nifti).load()
    rgb = reader.get_slice_rgb(5, axis=0)
    assert rgb.shape == (32, 20, 3)
    assert rgb.dtype == np.uint8


def test_reader_not_loaded():
    reader = NiftiReader("/nonexistent.nii.gz")
    with pytest.raises(RuntimeError, match="not loaded"):
        _ = reader.shape


# ─── save_mask_nifti ──────────────────────────────────────────────────────────


def test_save_mask_nifti(tmp_path):
    mask = np.zeros((32, 32, 20), dtype=np.uint8)
    mask[10:20, 10:20, 5:15] = 1
    out_path = tmp_path / "mask.nii.gz"
    result = save_mask_nifti(mask, out_path)

    assert result.exists()
    loaded = nib.load(str(result)).get_fdata().astype(np.uint8)
    np.testing.assert_array_equal(loaded, mask)


# ─── save_overlay_png ─────────────────────────────────────────────────────────


def test_save_overlay_png(tmp_path):
    img = np.random.rand(64, 64).astype(np.float32)
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[20:44, 20:44] = 1

    out_path = tmp_path / "overlay.png"
    result = save_overlay_png(img, mask, out_path)
    assert result.exists()


def test_save_overlay_png_with_prompts(tmp_path):
    img = np.random.rand(64, 64).astype(np.float32)
    mask = np.zeros((64, 64), dtype=np.uint8)
    prompts = [
        {"type": "box", "x1": 10, "y1": 10, "x2": 40, "y2": 40},
        {"type": "point", "x": 25, "y": 25, "label": 1},
    ]
    out_path = tmp_path / "overlay_prompts.png"
    result = save_overlay_png(img, mask, out_path, prompts=prompts)
    assert result.exists()


# ─── save_prompts_json ────────────────────────────────────────────────────────


def test_save_prompts_json(tmp_path):
    data = {
        "organ": "right kidney",
        "prompts": [{"slice_idx": 5, "box": [10, 20, 100, 150]}],
    }
    out_path = tmp_path / "prompts.json"
    result = save_prompts_json(data, out_path)
    assert result.exists()

    import json
    with open(result) as f:
        loaded = json.load(f)
    assert loaded["organ"] == "right kidney"
