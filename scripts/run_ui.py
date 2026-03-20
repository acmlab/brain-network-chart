#!/usr/bin/env python3
"""
Launch the MedSAM Agent Gradio web UI.

Usage
-----
  python scripts/run_ui.py
  python scripts/run_ui.py --port 7861 --share
  python scripts/run_ui.py --backend mock   # offline demo, no GPU needed
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure medsam/ root is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.ui.gradio_app import launch_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch MedSAM Agent UI")
    parser.add_argument("--port", type=int, default=7860, help="Gradio server port")
    parser.add_argument("--share", action="store_true", help="Create Gradio share link")
    parser.add_argument("--debug", action="store_true", help="Enable Gradio debug mode")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print(f"\n{'='*60}")
    print("  MedSAM Agent — Interactive Segmentation UI")
    print(f"  URL: http://localhost:{args.port}")
    print(f"{'='*60}\n")

    launch_app(port=args.port, share=args.share, debug=args.debug)


if __name__ == "__main__":
    main()
