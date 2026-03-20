"""
Segmentation evaluation metrics.

Computes Dice, IoU, Precision, Recall, HD95, and Volume Difference.

Usage
-----
>>> metrics = compute_all_metrics(pred_mask, gt_mask, voxel_spacing=(1.5, 1.5, 2.0))
>>> print(metrics["dice"], metrics["hd95"])

Notes
-----
- HD95 uses `medpy` if installed; falls back to a scipy-based approximation.
- All metrics gracefully handle empty masks (return NaN with a warning).
- "No GT" is a first-class state: this module is only called when GT exists.
"""

from __future__ import annotations

import logging
import warnings
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ─── Individual metrics ───────────────────────────────────────────────────────


def dice_score(pred: np.ndarray, gt: np.ndarray) -> float:
    """Dice coefficient (F1 score for binary masks).

    Returns NaN if both masks are empty.
    """
    pred_b = (pred > 0).astype(np.uint8)
    gt_b = (gt > 0).astype(np.uint8)
    intersection = float((pred_b & gt_b).sum())
    denom = float(pred_b.sum() + gt_b.sum())
    if denom == 0:
        logger.warning("Both pred and GT are empty — Dice is undefined.")
        return float("nan")
    return 2.0 * intersection / denom


def iou_score(pred: np.ndarray, gt: np.ndarray) -> float:
    """Intersection over Union (Jaccard index)."""
    pred_b = (pred > 0).astype(np.uint8)
    gt_b = (gt > 0).astype(np.uint8)
    intersection = float((pred_b & gt_b).sum())
    union = float((pred_b | gt_b).sum())
    if union == 0:
        return float("nan")
    return intersection / union


def precision_score(pred: np.ndarray, gt: np.ndarray) -> float:
    """Pixel-level precision: TP / (TP + FP)."""
    pred_b = (pred > 0).astype(np.uint8)
    gt_b = (gt > 0).astype(np.uint8)
    tp = float((pred_b & gt_b).sum())
    fp = float(pred_b.sum()) - tp
    if tp + fp == 0:
        return float("nan")
    return tp / (tp + fp)


def recall_score(pred: np.ndarray, gt: np.ndarray) -> float:
    """Pixel-level recall (sensitivity): TP / (TP + FN)."""
    pred_b = (pred > 0).astype(np.uint8)
    gt_b = (gt > 0).astype(np.uint8)
    tp = float((pred_b & gt_b).sum())
    fn = float(gt_b.sum()) - tp
    if tp + fn == 0:
        return float("nan")
    return tp / (tp + fn)


def volume_difference(
    pred: np.ndarray,
    gt: np.ndarray,
    voxel_spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> Dict[str, float]:
    """Absolute and relative volume difference in mm³."""
    voxel_vol = float(voxel_spacing[0] * voxel_spacing[1] * voxel_spacing[2])
    pred_vol = float((pred > 0).sum()) * voxel_vol
    gt_vol = float((gt > 0).sum()) * voxel_vol
    abs_diff = abs(pred_vol - gt_vol)
    rel_diff = abs_diff / max(gt_vol, 1e-6)
    return {
        "pred_volume_mm3": pred_vol,
        "gt_volume_mm3": gt_vol,
        "volume_diff_mm3": abs_diff,
        "volume_diff_pct": rel_diff * 100.0,
    }


def hd95_score(
    pred: np.ndarray,
    gt: np.ndarray,
    voxel_spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> float:
    """95th percentile Hausdorff distance in mm.

    Tries medpy first; falls back to scipy-based implementation.
    """
    pred_b = (pred > 0).astype(bool)
    gt_b = (gt > 0).astype(bool)

    if not pred_b.any() or not gt_b.any():
        logger.warning("Empty mask encountered in HD95 — returning NaN.")
        return float("nan")

    # Try medpy
    try:
        from medpy.metric.binary import hd95  # type: ignore
        return float(hd95(pred_b, gt_b, voxelspacing=voxel_spacing))
    except ImportError:
        pass

    # Fallback: scipy-based surface distance
    return _hd95_scipy(pred_b, gt_b, voxel_spacing)


def _hd95_scipy(
    pred: np.ndarray,
    gt: np.ndarray,
    voxel_spacing: Tuple[float, float, float],
) -> float:
    """HD95 via scipy distance transform (slower but no medpy dependency)."""
    from scipy.ndimage import distance_transform_edt

    # Scale voxel spacing for distance transform
    # DT returns Euclidean distance in voxel units; multiply by spacing
    pred_surf = _surface_voxels(pred)
    gt_surf = _surface_voxels(gt)

    if not pred_surf.any() or not gt_surf.any():
        return float("nan")

    # Distance from pred surface to gt
    dt_gt = distance_transform_edt(~gt, sampling=voxel_spacing)
    dist_pred_to_gt = dt_gt[pred_surf]

    # Distance from gt surface to pred
    dt_pred = distance_transform_edt(~pred, sampling=voxel_spacing)
    dist_gt_to_pred = dt_pred[gt_surf]

    all_dists = np.concatenate([dist_pred_to_gt, dist_gt_to_pred])
    return float(np.percentile(all_dists, 95))


def _surface_voxels(mask: np.ndarray) -> np.ndarray:
    """Return boolean array of surface voxels (True where mask borders background)."""
    from scipy.ndimage import binary_erosion
    eroded = binary_erosion(mask)
    return mask & ~eroded


# ─── Aggregated metrics ───────────────────────────────────────────────────────


def compute_all_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    voxel_spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    compute_hd95: bool = True,
) -> Dict[str, float]:
    """Compute all segmentation metrics.

    Parameters
    ----------
    pred:
        Binary (or multi-label) prediction mask.
    gt:
        Binary (or multi-label) ground-truth mask.
    voxel_spacing:
        (dx, dy, dz) in mm.
    compute_hd95:
        Whether to compute HD95 (can be slow for large volumes).

    Returns
    -------
    Dict with keys: dice, iou, precision, recall, hd95 (if computed),
    pred_volume_mm3, gt_volume_mm3, volume_diff_mm3, volume_diff_pct.
    """
    # Binarize (support multi-label by treating any nonzero as foreground)
    pred_b = (pred > 0).astype(np.uint8)
    gt_b = (gt > 0).astype(np.uint8)

    metrics: Dict[str, float] = {
        "dice": dice_score(pred_b, gt_b),
        "iou": iou_score(pred_b, gt_b),
        "precision": precision_score(pred_b, gt_b),
        "recall": recall_score(pred_b, gt_b),
    }

    if compute_hd95:
        try:
            metrics["hd95"] = hd95_score(pred_b, gt_b, voxel_spacing=voxel_spacing)
        except Exception as exc:
            logger.warning(f"HD95 failed: {exc}")
            metrics["hd95"] = float("nan")

    vol_metrics = volume_difference(pred_b, gt_b, voxel_spacing=voxel_spacing)
    metrics.update(vol_metrics)

    logger.info(
        f"Metrics — Dice: {metrics['dice']:.4f}, IoU: {metrics['iou']:.4f}, "
        f"HD95: {metrics.get('hd95', 'N/A')}"
    )
    return metrics
