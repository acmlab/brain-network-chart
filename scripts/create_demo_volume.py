#!/usr/bin/env python3
"""
Create a synthetic NIfTI volume for offline demos and tests.

Usage
-----
  python scripts/create_demo_volume.py --output output/demo.nii.gz
  python scripts/create_demo_volume.py --with-mask   # also creates GT mask
"""

import argparse
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.io import nifti_utils as _nu


def create_synthetic_volume(shape=(60, 128, 128), with_mask=False):
    """Create a synthetic 3D MR-like volume with an ellipsoidal 'organ'.

    Returns (volume, mask) — mask is None if with_mask=False.
    """
    D, H, W = shape
    rng = np.random.default_rng(42)

    # Background: low intensity Gaussian noise
    vol = rng.normal(loc=0.2, scale=0.05, size=(H, W, D)).astype(np.float32)
    vol = np.clip(vol, 0, 1)

    # Simulated tissue: ellipsoid in center
    cx, cy, cz = H // 2, W // 2, D // 2
    Y, X, Z = np.ogrid[:H, :W, :D]
    # Kidney-like ellipsoid
    ellipsoid = (
        ((Y - cx) / (H * 0.2)) ** 2 +
        ((X - cy) / (W * 0.15)) ** 2 +
        ((Z - cz) / (D * 0.25)) ** 2
    ) <= 1.0
    vol[ellipsoid] = rng.normal(loc=0.7, scale=0.08, size=ellipsoid.sum()).clip(0.4, 1.0)

    # Add some texture gradient
    gradient = np.linspace(0, 0.15, H)[:, None, None]
    vol += gradient
    vol = np.clip(vol, 0, 1)

    mask = ellipsoid.astype(np.uint8) if with_mask else None
    return vol, mask


def main():
    p = argparse.ArgumentParser(description="Create synthetic NIfTI demo volume")
    p.add_argument("--output", "-o", default="output/demo_volume.nii.gz")
    p.add_argument("--shape", nargs=3, type=int, default=[60, 128, 128],
                   metavar=("D", "H", "W"), help="Volume shape (D H W)")
    p.add_argument("--with-mask", action="store_true", help="Also save GT mask")
    args = p.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    shape = tuple(args.shape)
    vol, mask = create_synthetic_volume(shape=shape, with_mask=args.with_mask)

    # NIfTI convention: (H, W, D)
    affine = np.diag([1.5, 1.5, 2.0, 1.0])  # ~1.5mm isotropic, 2mm axial
    _nu.save_nifti(vol, out_path, affine=affine)
    print(f"✅ Demo volume saved: {out_path}  shape={vol.shape}")

    if mask is not None:
        mask_path = out_path.parent / (out_path.stem.replace(".nii", "") + "_gt_mask.nii.gz")
        _nu.save_mask_nifti(mask, mask_path, reference_affine=affine)
        print(f"✅ GT mask saved: {mask_path}")

    print(f"\nTo run single-case inference:")
    print(f"  python scripts/run_single_case.py \\")
    print(f"    --input {out_path} --backend mock \\")
    print(f"    --slice {shape[0]//2} --box 40 40 90 90 --propagate")


if __name__ == "__main__":
    main()
