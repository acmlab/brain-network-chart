#!/usr/bin/env python3
"""
Batch inference over a directory of NIfTI files.

Prompts can be supplied in two ways:
  A) A single JSON file with per-case prompts (keyed by filename stem).
  B) A fixed prompt applied to every case (e.g., --box for a fixed slice).

Usage
-----
  # Run all .nii.gz files in a directory with a fixed box prompt
  python scripts/run_batch.py \
    --input-dir /proj/data/UKB_KidneyMRI_ShMOLLI \
    --organ "right kidney" \
    --slice 45 --box 80 60 200 180 \
    --propagate

  # With per-case prompts JSON
  python scripts/run_batch.py \
    --input-dir /proj/data/UKB_KidneyMRI_ShMOLLI \
    --per-case-prompts all_prompts.json \
    --propagate

  # With GT masks directory for evaluation
  python scripts/run_batch.py \
    --input-dir /proj/data/UKB_KidneyMRI_ShMOLLI \
    --gt-dir /proj/data/UKB_KidneyMRI_masks \
    --box 80 60 200 180 --slice 45 --propagate
"""

import argparse
import csv
import json
import logging
import sys
import traceback
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
        description="MedSAM Agent — batch inference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--input-dir", "-i", required=True, help="Directory with NIfTI files")
    p.add_argument("--organ", default="custom")
    p.add_argument("--axis", type=int, default=0, choices=[0, 1, 2])
    p.add_argument("--slice", type=int, default=None, dest="slice_idx")
    p.add_argument("--box", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"))
    p.add_argument("--per-case-prompts", help="JSON file: {stem: prompts_dict}")
    p.add_argument("--propagate", action="store_true")
    p.add_argument("--gt-dir", help="Directory with GT masks (filename must match input)")
    p.add_argument("--output", help="Output root directory")
    p.add_argument("--backend", default="medsam", choices=["medsam", "medsam2", "sam", "mock"])
    p.add_argument("--norm", default="percentile",
                   choices=["percentile", "window", "minmax"])
    p.add_argument("--pattern", default="*.nii.gz", help="Glob pattern for input files")
    p.add_argument("--max-cases", type=int, default=None, help="Limit number of cases")
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
    out_root = Path(args.output or cfg["output"]["base_dir"])

    # ── Find input files ───────────────────────────────────────────────────────
    input_dir = Path(args.input_dir)
    files = sorted(input_dir.glob(args.pattern))
    if args.max_cases:
        files = files[: args.max_cases]

    if not files:
        log.error(f"No files matching {args.pattern!r} in {input_dir}")
        sys.exit(1)

    log.info(f"Found {len(files)} cases in {input_dir}")

    # ── Load per-case prompts (optional) ─────────────────────────────────────
    per_case_prompts: dict = {}
    if args.per_case_prompts:
        with open(args.per_case_prompts, "r") as f:
            per_case_prompts = json.load(f)

    # ── Load model (shared across all cases) ─────────────────────────────────
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

    # ── Batch loop ─────────────────────────────────────────────────────────────
    summary_rows = []

    for i, vol_path in enumerate(files):
        stem = vol_path.name.replace(".nii.gz", "").replace(".nii", "")
        log.info(f"\n[{i+1}/{len(files)}] Processing: {vol_path.name}")

        # GT mask lookup
        gt_path = None
        if args.gt_dir:
            gt_dir = Path(args.gt_dir)
            candidates = list(gt_dir.glob(f"{stem}*"))
            if candidates:
                gt_path = str(candidates[0])
                log.info(f"  GT mask: {gt_path}")

        try:
            orch = SegmentationOrchestrator(
                adapter=adapter,
                output_dir=out_root,
                propagation_strategy=cfg["propagation"]["strategy"],
            )
            orch.new_session(
                volume_path=vol_path,
                organ=args.organ,
                axis=args.axis,
                norm_method=args.norm,
                gt_mask_path=gt_path,
                case_id=stem,
            )

            # Add prompts
            if stem in per_case_prompts:
                pm = PromptManager.from_dict(per_case_prompts[stem])
                orch._prompt_manager = pm  # type: ignore[attr-defined]
            elif args.box and args.slice_idx is not None:
                orch.add_box_prompt(args.slice_idx, args.box, axis=args.axis)
            else:
                log.warning(f"  No prompts for {stem}. Skipping.")
                continue

            # Inference
            if args.propagate:
                orch.propagate_to_volume()
            else:
                for idx in orch.prompt_manager.prompted_slices():
                    orch.segment_slice(idx)

            # Save
            out = orch.save_outputs()

            # Metrics
            metrics = orch.compute_metrics() or {}

            row = {
                "case": stem,
                "status": "ok",
                **{k: f"{v:.4f}" if isinstance(v, float) else v
                   for k, v in metrics.items()},
            }
            summary_rows.append(row)
            log.info(f"  ✅ Done: {out.get('mask', '')}")

        except Exception as exc:
            tb = traceback.format_exc()
            log.error(f"  ❌ Failed: {exc}\n{tb}")
            summary_rows.append({"case": stem, "status": "error", "error": str(exc)})

    # ── Write summary CSV ──────────────────────────────────────────────────────
    summary_path = out_root / "batch_summary.csv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    if summary_rows:
        all_keys = list({k for row in summary_rows for k in row.keys()})
        with open(summary_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\n=== Batch complete ===")
    print(f"  Cases: {len(files)} | Success: {sum(r['status']=='ok' for r in summary_rows)}")
    print(f"  Summary: {summary_path}")


if __name__ == "__main__":
    main()
