#!/usr/bin/env python3
"""
Run inference on a single NIfTI case from the command line.

Usage
-----
  # With a box prompt (single slice)
  python scripts/run_single_case.py \
    --input /proj/data/UKB_KidneyMRI_ShMOLLI/sub-001.nii.gz \
    --organ "right kidney" \
    --slice 45 \
    --box 80 60 200 180

  # With a prompts JSON file (multiple slices)
  python scripts/run_single_case.py \
    --input sub-001.nii.gz \
    --prompts prompts.json \
    --propagate

  # With GT mask for evaluation
  python scripts/run_single_case.py \
    --input sub-001.nii.gz \
    --box 80 60 200 180 \
    --gt sub-001_mask.nii.gz \
    --slice 45

  # Offline demo (no GPU / model weights needed)
  python scripts/run_single_case.py --input demo.nii.gz --backend mock \
    --box 50 50 150 150 --slice 10 --propagate
"""

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config_loader import load_config
from app.models import load_adapter
from app.agent.orchestrator import SegmentationOrchestrator
from app.agent.prompt_manager import PromptManager


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MedSAM Agent — single case inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--input", "-i", required=True, help="Input NIfTI path")
    p.add_argument("--organ", "-o", default="custom", help="Target organ name")
    p.add_argument("--axis", type=int, default=0, choices=[0, 1, 2], help="Slicing axis")
    p.add_argument("--slice", "-s", type=int, default=None, dest="slice_idx",
                   help="Slice index to add prompt on")
    p.add_argument("--box", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"),
                   help="Bounding box prompt [x1 y1 x2 y2]")
    p.add_argument("--prompts", help="Path to prompts JSON (alternative to --box)")
    p.add_argument("--propagate", action="store_true",
                   help="Propagate to full volume after prompted slices")
    p.add_argument("--gt", help="Optional GT mask .nii.gz for evaluation")
    p.add_argument("--output", help="Output directory (overrides config)")
    p.add_argument("--backend", default="medsam",
                   choices=["medsam", "medsam2", "sam", "mock"], help="Model backend")
    p.add_argument("--norm", default="percentile",
                   choices=["percentile", "window", "minmax"],
                   help="Intensity normalization method")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger(__name__)

    cfg = load_config()
    out_dir = args.output or cfg["output"]["base_dir"]

    # ── Load model ────────────────────────────────────────────────────────────
    log.info(f"Loading backend: {args.backend}")
    adapter = load_adapter(
        args.backend,
        device=cfg["model"]["device"],
        segment_anything_path=cfg["model"].get("segment_anything_path", ""),
        medsam2_repo_path=cfg["model"].get("medsam2_repo_path", ""),
    )
    if args.backend in ("medsam", "sam"):
        adapter.load_model(
            cfg["model"]["checkpoint"],
            segment_anything_path=cfg["model"].get("segment_anything_path", ""),
        )
    elif args.backend == "medsam2":
        adapter.load_model(
            cfg["model"]["medsam2_checkpoint"],
            medsam2_repo_path=cfg["model"].get("medsam2_repo_path", ""),
            config_file=cfg["model"].get("medsam2_config"),
        )
    else:
        adapter.load_model()

    # ── Create orchestrator ────────────────────────────────────────────────────
    orch = SegmentationOrchestrator(
        adapter=adapter,
        output_dir=out_dir,
        propagation_strategy=cfg["propagation"]["strategy"],
    )
    orch.new_session(
        volume_path=args.input,
        organ=args.organ,
        axis=args.axis,
        norm_method=args.norm,
        gt_mask_path=args.gt,
    )
    log.info(f"Volume loaded: {orch.reader.shape}")

    # ── Load prompts ───────────────────────────────────────────────────────────
    if args.prompts:
        pm = PromptManager.load(args.prompts)
        orch._prompt_manager = pm  # type: ignore[attr-defined]
        log.info(
            f"Loaded {pm.num_prompted_slices()} prompted slices from {args.prompts}"
        )
    elif args.box and args.slice_idx is not None:
        orch.add_box_prompt(args.slice_idx, args.box, axis=args.axis)
        log.info(f"Box prompt: slice={args.slice_idx}, box={args.box}")
    else:
        log.warning(
            "No prompts provided. Use --box and --slice, or --prompts."
            "\nRunning with empty mask."
        )

    # ── Inference ──────────────────────────────────────────────────────────────
    if args.propagate:
        log.info("Propagating to full volume...")
        mask = orch.propagate_to_volume()
        log.info(f"Done. Foreground voxels: {int(mask.sum()):,}")
    else:
        for idx in orch.prompt_manager.prompted_slices():
            log.info(f"Segmenting slice {idx}...")
            orch.segment_slice(idx)

    # ── Save outputs ───────────────────────────────────────────────────────────
    out = orch.save_outputs()
    print("\n=== Outputs ===")
    for k, v in out.items():
        print(f"  {k}: {v}")

    # ── Metrics ────────────────────────────────────────────────────────────────
    if args.gt:
        metrics = orch.compute_metrics()
        if metrics:
            print("\n=== Metrics ===")
            for k, v in metrics.items():
                if isinstance(v, float):
                    print(f"  {k}: {v:.4f}")
                else:
                    print(f"  {k}: {v}")
    else:
        print("\n[INFO] No GT mask provided — metrics not computed (inference-only mode).")


if __name__ == "__main__":
    main()
