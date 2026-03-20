"""
Session: immutable record of one segmentation case.

Tracks case metadata, inference events, propagation events, and output paths.
This is the audit trail and state container — it does NOT do computation.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..models.base_adapter import SegResult

logger = logging.getLogger(__name__)


class Session:
    """Holds all metadata and history for one segmentation session.

    Attributes
    ----------
    case_id:
        Unique identifier (usually derived from the filename).
    volume_path:
        Path to the input NIfTI file.
    organ:
        Target organ / structure name.
    axis:
        Primary slicing axis used in this session.
    volume_shape:
        Shape of the loaded volume (H, W, D).
    gt_mask:
        Ground-truth mask array if provided; None otherwise.
    case_dir:
        Output directory for this case.
    events:
        Ordered list of logged events (inference, propagation, etc.).
    """

    def __init__(
        self,
        case_id: str,
        volume_path: Path,
        organ: str,
        axis: int,
        volume_shape: Tuple[int, ...],
        output_dir: Path,
        gt_mask: Optional[np.ndarray] = None,
    ):
        self.case_id = case_id
        self.volume_path = volume_path
        self.organ = organ
        self.axis = axis
        self.volume_shape = volume_shape
        self.gt_mask = gt_mask
        self.has_gt = gt_mask is not None

        self.case_dir = output_dir
        self.started_at = datetime.utcnow().isoformat()
        self.events: List[Dict[str, Any]] = []

        if not self.has_gt:
            logger.info(
                "[Session] No ground-truth mask provided — running in inference-only mode. "
                "Metrics will not be computed."
            )
        else:
            logger.info("[Session] GT mask loaded — evaluation mode active.")

    # ── Event recording ───────────────────────────────────────────────────────

    def record_inference(self, slice_idx: int, result: SegResult) -> None:
        """Log a completed slice inference."""
        self.events.append(
            {
                "type": "inference",
                "timestamp": datetime.utcnow().isoformat(),
                "slice_idx": slice_idx,
                "mask_area": int(result.mask.sum()),
                "confidence": result.confidence,
            }
        )

    def record_propagation(self, elapsed_sec: float, total_fg_voxels: int) -> None:
        """Log a completed volume propagation."""
        self.events.append(
            {
                "type": "propagation",
                "timestamp": datetime.utcnow().isoformat(),
                "elapsed_sec": round(elapsed_sec, 2),
                "total_fg_voxels": total_fg_voxels,
            }
        )

    def record_metrics(self, metrics: Dict[str, Any]) -> None:
        """Log computed evaluation metrics."""
        self.events.append(
            {
                "type": "metrics",
                "timestamp": datetime.utcnow().isoformat(),
                **metrics,
            }
        )

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "volume_path": str(self.volume_path),
            "organ": self.organ,
            "axis": self.axis,
            "volume_shape": list(self.volume_shape),
            "has_gt": self.has_gt,
            "started_at": self.started_at,
            "events": self.events,
        }

    def save_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Session log saved: {path}")
