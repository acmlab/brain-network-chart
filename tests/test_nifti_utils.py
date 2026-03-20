"""
Tests for app.io.nifti_utils — the unified NIfTI utility layer.

Covers:
  - load_nifti / load_nifti_with_meta (3D and 4D)
  - ensure_3d
  - normalize_intensity (all modes)
  - NaN / Inf handling
  - Constant-volume handling
  - get_slice / set_slice for all 3 axes
  - get_slice_uint8 / get_slice_rgb
  - get_voxel_spacing
  - compute_physical_volume
  - save_nifti / save_mask_nifti round-trip
"""

from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.io.nifti_utils import (
    load_nifti,
    load_nifti_with_meta,
    NiftiMeta,
    normalize_intensity,
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
    compute_physical_volume,
    save_nifti,
    save_mask_nifti,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_nifti_3d(tmp_path) -> Path:
    """Create a 3D NIfTI file with known spacing."""
    vol = np.random.default_rng(42).normal(100, 30, (32, 48, 20)).astype(np.float32)
    affine = np.diag([1.5, 1.5, 2.0, 1.0])
    nii = nib.Nifti1Image(vol, affine)
    path = tmp_path / "vol3d.nii.gz"
    nib.save(nii, str(path))
    return path


@pytest.fixture
def tmp_nifti_4d(tmp_path) -> Path:
    """Create a 4D NIfTI file (3 temporal frames)."""
    vol = np.ones((16, 24, 10, 3), dtype=np.float32)
    vol[..., 0] = 1.0
    vol[..., 1] = 2.0
    vol[..., 2] = 3.0
    nii = nib.Nifti1Image(vol, np.eye(4))
    path = tmp_path / "vol4d.nii.gz"
    nib.save(nii, str(path))
    return path


# ═══════════════════════════════════════════════════════════════════════════════
#  A.  Loading
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadNifti:
    def test_basic_3d(self, tmp_nifti_3d):
        vol, aff, hdr = load_nifti(tmp_nifti_3d)
        assert vol.ndim == 3
        assert vol.shape == (32, 48, 20)
        assert vol.dtype == np.float32
        assert aff.shape == (4, 4)

    def test_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_nifti("/no/such/file.nii.gz")

    def test_4d_collapsed(self, tmp_nifti_4d):
        vol, _, _ = load_nifti(tmp_nifti_4d)
        assert vol.ndim == 3
        assert vol.shape == (16, 24, 10)
        # First frame should be all 1.0
        assert np.allclose(vol, 1.0)


class TestLoadNiftiWithMeta:
    def test_returns_niftimeta(self, tmp_nifti_3d):
        meta = load_nifti_with_meta(tmp_nifti_3d)
        assert isinstance(meta, NiftiMeta)
        assert meta.shape == (32, 48, 20)
        assert meta.dtype == np.float32
        assert len(meta.spacing) == 3
        assert meta.spacing == pytest.approx((1.5, 1.5, 2.0), abs=0.01)

    def test_repr(self, tmp_nifti_3d):
        meta = load_nifti_with_meta(tmp_nifti_3d)
        r = repr(meta)
        assert "NiftiMeta" in r
        assert "32" in r


# ═══════════════════════════════════════════════════════════════════════════════
#  ensure_3d
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnsure3D:
    def test_3d_passthrough(self):
        v = np.zeros((5, 6, 7))
        assert ensure_3d(v) is v

    def test_4d_collapse(self):
        v = np.ones((5, 6, 7, 3))
        out = ensure_3d(v)
        assert out.shape == (5, 6, 7)

    def test_2d_expand(self):
        v = np.zeros((5, 6))
        out = ensure_3d(v)
        assert out.shape == (5, 6, 1)

    def test_1d_raises(self):
        with pytest.raises(ValueError, match="ndim"):
            ensure_3d(np.zeros(10))


# ═══════════════════════════════════════════════════════════════════════════════
#  B.  Normalization
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalization:

    def test_percentile(self):
        vol = np.arange(100, dtype=np.float32).reshape(10, 10, 1)
        out = normalize_intensity(vol, method="percentile", low=0, high=100)
        assert out.min() >= 0.0
        assert out.max() <= 1.0
        assert out.dtype == np.float32

    def test_window(self):
        vol = np.linspace(-100, 500, 100, dtype=np.float32).reshape(10, 10, 1)
        out = normalize_intensity(vol, method="window", center=100, width=200)
        assert out.min() >= 0.0
        assert out.max() <= 1.0

    def test_minmax(self):
        vol = np.array([[[0.0], [5.0], [10.0]]], dtype=np.float32)
        out = normalize_intensity(vol, method="minmax")
        assert out.min() == pytest.approx(0.0)
        assert out.max() == pytest.approx(1.0)

    def test_zscore(self):
        vol = np.random.default_rng(0).normal(50, 10, (20, 20, 5)).astype(np.float32)
        out = normalize_intensity(vol, method="zscore")
        assert out.dtype == np.float32
        # z-score output should be roughly mean=0, std=1
        assert abs(out.mean()) < 0.1
        assert abs(out.std() - 1.0) < 0.1

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            normalize_intensity(np.zeros((3, 3, 3)), method="bogus")

    def test_custom_out_range(self):
        vol = np.arange(100, dtype=np.float32).reshape(10, 10, 1)
        out = normalize_intensity(vol, method="minmax", out_range=(-1.0, 1.0))
        assert out.min() >= -1.0
        assert out.max() <= 1.0

    def test_constant_volume(self):
        vol = np.full((5, 5, 5), 42.0, dtype=np.float32)
        out = normalize_intensity(vol, method="percentile")
        assert np.all(out == 0.0)

    def test_nan_handling(self):
        vol = np.array([[[1.0, 2.0, np.nan], [4.0, 5.0, 6.0]]], dtype=np.float32)
        out = normalize_intensity(vol, method="minmax")
        assert not np.any(np.isnan(out))
        assert out.dtype == np.float32

    def test_inf_handling(self):
        vol = np.array([[[1.0, np.inf, 3.0], [4.0, -np.inf, 6.0]]], dtype=np.float32)
        out = normalize_intensity(vol, method="minmax")
        assert not np.any(np.isinf(out))


class TestClipPercentile:
    def test_basic(self):
        vol = np.arange(1000, dtype=np.float32).reshape(10, 10, 10)
        out = clip_percentile(vol, low=5, high=95)
        assert out.min() >= 0.0
        assert out.max() <= 1.0


class TestWindowIntensity:
    def test_basic(self):
        vol = np.linspace(-200, 600, 1000, dtype=np.float32).reshape(10, 10, 10)
        out = window_intensity(vol, center=40, width=400)
        assert out.min() >= 0.0
        assert out.max() <= 1.0


class TestMinmaxNormalize:
    def test_basic(self):
        vol = np.array([0.0, 5.0, 10.0], dtype=np.float32).reshape(1, 1, 3)
        out = minmax_normalize(vol)
        np.testing.assert_allclose(out.ravel(), [0.0, 0.5, 1.0])


class TestZscoreNormalize:
    def test_with_mask(self):
        vol = np.zeros((10, 10, 1), dtype=np.float32)
        vol[3:7, 3:7, :] = 100.0
        mask = np.zeros_like(vol, dtype=np.uint8)
        mask[3:7, 3:7, :] = 1
        out = zscore_normalize(vol, mask=mask)
        # Inside the mask all values are the same → std≈0 → zeros
        assert np.all(out == 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  C.  Slice Extraction / Mutation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSliceOps:
    @pytest.fixture
    def vol(self):
        return np.arange(60, dtype=np.float32).reshape(3, 4, 5)

    def test_get_slice_axis0(self, vol):
        sl = get_slice(vol, 1, axis=0)
        assert sl.shape == (4, 5)
        np.testing.assert_array_equal(sl, vol[1, :, :])

    def test_get_slice_axis1(self, vol):
        sl = get_slice(vol, 2, axis=1)
        assert sl.shape == (3, 5)
        np.testing.assert_array_equal(sl, vol[:, 2, :])

    def test_get_slice_axis2(self, vol):
        sl = get_slice(vol, 4, axis=2)
        assert sl.shape == (3, 4)
        np.testing.assert_array_equal(sl, vol[:, :, 4])

    def test_get_slice_clamps(self, vol):
        # Negative index → clamped to 0
        sl = get_slice(vol, -1, axis=0)
        np.testing.assert_array_equal(sl, vol[0, :, :])
        # Beyond max → clamped to last
        sl = get_slice(vol, 999, axis=0)
        np.testing.assert_array_equal(sl, vol[2, :, :])

    def test_get_slice_bad_axis(self, vol):
        with pytest.raises(ValueError, match="axis"):
            get_slice(vol, 0, axis=5)

    def test_set_slice_axis0(self, vol):
        data = np.ones((4, 5), dtype=np.float32) * 99.0
        set_slice(vol, 0, data, axis=0)
        np.testing.assert_array_equal(vol[0, :, :], data)

    def test_set_slice_axis1(self, vol):
        data = np.ones((3, 5), dtype=np.float32) * 77.0
        set_slice(vol, 1, data, axis=1)
        np.testing.assert_array_equal(vol[:, 1, :], data)

    def test_set_slice_axis2(self, vol):
        data = np.ones((3, 4), dtype=np.float32) * 55.0
        set_slice(vol, 3, data, axis=2)
        np.testing.assert_array_equal(vol[:, :, 3], data)

    def test_num_slices(self, vol):
        assert num_slices(vol, axis=0) == 3
        assert num_slices(vol, axis=1) == 4
        assert num_slices(vol, axis=2) == 5


class TestSliceUint8:
    def test_normalized(self):
        vol = np.linspace(0, 1, 60, dtype=np.float32).reshape(3, 4, 5)
        sl = get_slice_uint8(vol, 1, axis=0, normalized=True)
        assert sl.dtype == np.uint8
        assert sl.shape == (4, 5)

    def test_unnormalized(self):
        vol = np.arange(60, dtype=np.float32).reshape(3, 4, 5)
        sl = get_slice_uint8(vol, 1, axis=0, normalized=False)
        assert sl.dtype == np.uint8


class TestSliceRGB:
    def test_rgb_shape(self):
        vol = np.random.default_rng(0).random((10, 12, 8)).astype(np.float32)
        rgb = get_slice_rgb(vol, 5, axis=0)
        assert rgb.shape == (12, 8, 3)
        assert rgb.dtype == np.uint8


# ═══════════════════════════════════════════════════════════════════════════════
#  D.  Metadata / Geometry
# ═══════════════════════════════════════════════════════════════════════════════


class TestMetadata:
    def test_get_voxel_spacing(self, tmp_nifti_3d):
        _, _, hdr = load_nifti(tmp_nifti_3d)
        sp = get_voxel_spacing(hdr)
        assert sp == pytest.approx((1.5, 1.5, 2.0), abs=0.01)

    def test_get_voxel_spacing_fallback(self):
        # Pass a dummy object without get_zooms
        sp = get_voxel_spacing(object())
        assert sp == (1.0, 1.0, 1.0)

    def test_orientation_info(self, tmp_nifti_3d):
        meta = load_nifti_with_meta(tmp_nifti_3d)
        info = get_orientation_info(meta.header)
        assert "axcodes" in info
        assert len(info["axcodes"]) == 3

    def test_compute_physical_volume(self):
        mask = np.zeros((10, 10, 10), dtype=np.uint8)
        mask[2:8, 2:8, 2:8] = 1
        # 6*6*6 = 216 voxels, each 2*2*2 = 8 mm³
        vol = compute_physical_volume(mask, spacing=(2.0, 2.0, 2.0))
        assert vol == pytest.approx(216 * 8.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  E.  Save / Round-trip
# ═══════════════════════════════════════════════════════════════════════════════


class TestSaveNifti:
    def test_save_and_reload(self, tmp_path):
        vol = np.random.default_rng(7).random((20, 30, 10)).astype(np.float32)
        affine = np.diag([1.0, 1.0, 1.0, 1.0])
        out = tmp_path / "saved.nii.gz"
        result = save_nifti(vol, out, affine=affine)
        assert result.exists()

        loaded, aff2, _ = load_nifti(result)
        np.testing.assert_allclose(loaded, vol, atol=1e-5)
        np.testing.assert_array_equal(aff2, affine)

    def test_save_with_dtype_cast(self, tmp_path):
        vol = np.ones((5, 5, 5), dtype=np.float64)
        out = tmp_path / "cast.nii.gz"
        save_nifti(vol, out, dtype=np.float32)
        loaded = nib.load(str(out)).get_fdata()
        assert loaded.dtype in (np.float32, np.float64)  # header may upcast

    def test_save_creates_parents(self, tmp_path):
        vol = np.zeros((3, 3, 3), dtype=np.float32)
        out = tmp_path / "deep" / "nested" / "dir" / "vol.nii.gz"
        save_nifti(vol, out)
        assert out.exists()


class TestSaveMaskNifti:
    def test_round_trip(self, tmp_path):
        mask = np.zeros((32, 32, 20), dtype=np.uint8)
        mask[10:20, 10:20, 5:15] = 1
        affine = np.diag([1.5, 1.5, 2.0, 1.0])
        out = tmp_path / "mask.nii.gz"
        result = save_mask_nifti(mask, out, reference_affine=affine)
        assert result.exists()

        loaded = nib.load(str(result)).get_fdata().astype(np.uint8)
        np.testing.assert_array_equal(loaded, mask)

    def test_no_affine(self, tmp_path):
        mask = np.ones((5, 5, 5), dtype=np.uint8)
        out = tmp_path / "mask_no_aff.nii.gz"
        result = save_mask_nifti(mask, out)
        assert result.exists()

    def test_creates_parents(self, tmp_path):
        mask = np.zeros((3, 3, 3), dtype=np.uint8)
        out = tmp_path / "a" / "b" / "mask.nii.gz"
        result = save_mask_nifti(mask, out)
        assert result.exists()
