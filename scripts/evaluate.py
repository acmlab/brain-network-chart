#!/usr/bin/env python3
"""
Evaluate a predicted mask against a ground-truth mask.

Usage
-----
  # Single case
  python scripts/evaluate.py \
    --pred output/sub-001/pred_mask.nii.gz \
    --gt /proj/data/gt_masks/sub-001_mask.nii.gz

  # Batch: directory of pred masks vs directory of GT masks
  python scripts/evaluate.py \
    --pred-dir output/ \
    --gt-dir /proj/data/gt_masks/ \
    --pattern "*/pred_mask.nii.gz"
"""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.eval.metrics import compute_all_metrics
from app.io import nifti_utils as _nu


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate segmentation mask against GT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Single case
    p.add_argument("--pred", help="Predicted mask .nii.gz")
    p.add_argument("--gt", help="GT mask .nii.gz")
    # Batch
    p.add_argument("--pred-dir", help="Root dir with predicted masks")
    p.add_argument("--gt-dir", help="Root dir with GT masks")
    p.add_argument("--pattern", default="*/pred_mask.nii.gz")
    # Options
    p.add_argument("--output", help="Output JSON path (single) or CSV (batch)")
    p.add_argument("--no-hd95", action="store_true", help="Skip HD95 (faster)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def load_mask(path: str | Path) -> tuple:
    """Return (mask_array, voxel_spacing)."""
    meta = _nu.load_nifti_with_meta(path)
    mask = meta.volume.astype(np.uint8)
    return mask, meta.spacing


def evaluate_pair(pred_path: Path, gt_path: Path, no_hd95: bool = False) -> dict:
    pred, spacing = load_mask(pred_path)
    gt, _ = load_mask(gt_path)

    if pred.shape != gt.shape:
        return {"error": f"Shape mismatch: pred={pred.shape} gt={gt.shape}"}

    return compute_all_metrics(pred, gt, voxel_spacing=spacing, compute_hd95=not no_hd95)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger(__name__)

    # ── Single case ────────────────────────────────────────────────────────────
    if args.pred and args.gt:
        metrics = evaluate_pair(
            Path(args.pred), Path(args.gt), no_hd95=args.no_hd95
        )
        print("\n=== Metrics ===")
        for k, v in metrics.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")

        out_path = args.output or Path(args.pred).parent / "metrics_eval.json"
        with open(out_path, "w") as f:
            json.dump(metrics, f, indent=2, default=lambda x: float(x) if isinstance(x, (float,)) else x)
        print(f"\nMetrics saved to: {out_path}")
        return

    # ── Batch ──────────────────────────────────────────────────────────────────
    if args.pred_dir and args.gt_dir:
        pred_dir = Path(args.pred_dir)
        gt_dir = Path(args.gt_dir)
        pred_files = sorted(pred_dir.glob(args.pattern))

        if not pred_files:
            log.error(f"No files matching {args.pattern!r} under {pred_dir}")
            sys.exit(1)

        rows = []
        for pred_path in pred_files:
            # Guess GT filename from case dir name
            case_id = pred_path.parent.name
            gt_candidates = list(gt_dir.glob(f"{case_id}*"))
            if not gt_candidates:
                log.warning(f"No GT found for {case_id}")
                rows.append({"case": case_id, "error": "no_gt"})
                continue

            gt_path = gt_candidates[0]
            log.info(f"Evaluating {case_id}: pred={pred_path.name} gt={gt_path.name}")

            try:
                metrics = evaluate_pair(pred_path, gt_path, no_hd95=args.no_hd95)
                rows.append({"case": case_id, **metrics})
            except Exception as exc:
                log.error(f"  Failed: {exc}")
                rows.append({"case": case_id, "error": str(exc)})

        # Print summary
        valid = [r for r in rows if "dice" in r]
        if valid:
            dice_vals = [r["dice"] for r in valid if isinstance(r.get("dice"), float)]
            print(f"\n=== Batch Summary ===")
            print(f"  Cases evaluated: {len(valid)}/{len(rows)}")
            if dice_vals:
                print(f"  Dice — mean: {np.mean(dice_vals):.4f}, "
                      f"std: {np.std(dice_vals):.4f}, "
                      f"median: {np.median(dice_vals):.4f}")

        # Save CSV
        out_path = args.output or str(pred_dir / "batch_metrics.csv")
        all_keys = list({k for r in rows for k in r.keys()})
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nMetrics saved to: {out_path}")
        return

    print("ERROR: Provide either (--pred + --gt) or (--pred-dir + --gt-dir).")
    sys.exit(1)


if __name__ == "__main__":
    main()
