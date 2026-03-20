"""Tests for segmentation evaluation metrics."""

import numpy as np
import pytest

from app.eval.metrics import (
    dice_score, iou_score, precision_score, recall_score,
    volume_difference, compute_all_metrics,
)


# ─── Perfect overlap ──────────────────────────────────────────────────────────


def test_dice_perfect():
    mask = np.zeros((50, 50, 20), dtype=np.uint8)
    mask[10:30, 10:30, 5:15] = 1
    assert dice_score(mask, mask) == pytest.approx(1.0)


def test_iou_perfect():
    mask = np.zeros((50, 50, 20), dtype=np.uint8)
    mask[10:30, 10:30, 5:15] = 1
    assert iou_score(mask, mask) == pytest.approx(1.0)


def test_precision_perfect():
    mask = np.zeros((50, 50, 20), dtype=np.uint8)
    mask[10:30, 10:30, 5:15] = 1
    assert precision_score(mask, mask) == pytest.approx(1.0)


def test_recall_perfect():
    mask = np.zeros((50, 50, 20), dtype=np.uint8)
    mask[10:30, 10:30, 5:15] = 1
    assert recall_score(mask, mask) == pytest.approx(1.0)


# ─── No overlap ───────────────────────────────────────────────────────────────


def test_dice_no_overlap():
    pred = np.zeros((50, 50, 20), dtype=np.uint8)
    gt = np.zeros((50, 50, 20), dtype=np.uint8)
    pred[0:10, 0:10, 0:5] = 1
    gt[40:50, 40:50, 15:20] = 1
    assert dice_score(pred, gt) == pytest.approx(0.0)


def test_iou_no_overlap():
    pred = np.zeros((50, 50, 20), dtype=np.uint8)
    gt = np.zeros((50, 50, 20), dtype=np.uint8)
    pred[0:10, 0:10, 0:5] = 1
    gt[40:50, 40:50, 15:20] = 1
    assert iou_score(pred, gt) == pytest.approx(0.0)


# ─── Empty masks ──────────────────────────────────────────────────────────────


def test_dice_both_empty():
    pred = np.zeros((10, 10, 5), dtype=np.uint8)
    gt = np.zeros((10, 10, 5), dtype=np.uint8)
    result = dice_score(pred, gt)
    assert np.isnan(result)


# ─── Partial overlap ─────────────────────────────────────────────────────────


def test_dice_partial():
    pred = np.zeros((10, 10, 1), dtype=np.uint8)
    gt = np.zeros((10, 10, 1), dtype=np.uint8)
    pred[0:6, 0:6, 0] = 1   # 36 voxels
    gt[4:10, 4:10, 0] = 1   # 36 voxels, 4 overlap
    d = dice_score(pred, gt)
    # intersection=4, sum=72, dice=8/72
    expected = 2 * 4 / (36 + 36)
    assert d == pytest.approx(expected, rel=1e-5)


# ─── Volume difference ────────────────────────────────────────────────────────


def test_volume_difference_equal():
    mask = np.ones((10, 10, 10), dtype=np.uint8)
    vd = volume_difference(mask, mask, voxel_spacing=(1.0, 1.0, 1.0))
    assert vd["volume_diff_mm3"] == pytest.approx(0.0)
    assert vd["volume_diff_pct"] == pytest.approx(0.0)


def test_volume_difference_known():
    pred = np.ones((10, 10, 10), dtype=np.uint8)  # 1000 voxels
    gt = np.zeros((10, 10, 10), dtype=np.uint8)
    gt[0:5, :, :] = 1   # 500 voxels
    vd = volume_difference(pred, gt, voxel_spacing=(2.0, 2.0, 2.0))
    # 1000 * 8 = 8000mm³ pred; 500 * 8 = 4000mm³ gt; diff = 4000
    assert vd["pred_volume_mm3"] == pytest.approx(8000.0)
    assert vd["gt_volume_mm3"] == pytest.approx(4000.0)
    assert vd["volume_diff_mm3"] == pytest.approx(4000.0)


# ─── compute_all_metrics ─────────────────────────────────────────────────────


def test_compute_all_metrics_keys():
    mask = np.zeros((20, 20, 10), dtype=np.uint8)
    mask[5:15, 5:15, 2:8] = 1
    metrics = compute_all_metrics(mask, mask, compute_hd95=False)
    assert "dice" in metrics
    assert "iou" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "pred_volume_mm3" in metrics
    assert metrics["dice"] == pytest.approx(1.0)
