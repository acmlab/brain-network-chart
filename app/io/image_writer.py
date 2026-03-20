"""
Output writers: NIfTI masks, PNG overlays, prompts JSON, metrics CSV/JSON.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# ── Re-export from the canonical location (nifti_utils is the single source) ─
from .nifti_utils import save_mask_nifti  # noqa: F401


# ─── PNG overlay writer ──────────────────────────────────────────────────────


def save_overlay_png(
    image_slice: np.ndarray,
    mask_slice: np.ndarray,
    out_path: str | Path,
    *,
    alpha: float = 0.4,
    mask_color: Tuple[int, int, int] = (255, 215, 0),
    prompts: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """Render a 2D greyscale slice with mask overlay and save as PNG.

    Parameters
    ----------
    image_slice:
        2D float [0,1] or uint8 array.
    mask_slice:
        2D binary uint8 array (1 = foreground).
    out_path:
        Destination .png path.
    alpha:
        Opacity of the mask overlay.
    mask_color:
        RGB tuple for the mask color.
    prompts:
        Optional list of prompt dicts to draw on top
        (each dict: type "box" with keys x1,y1,x2,y2,
                    or  "point" with keys x,y,label).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalise image to uint8
    if image_slice.dtype != np.uint8:
        img_u8 = (np.clip(image_slice, 0.0, 1.0) * 255).astype(np.uint8)
    else:
        img_u8 = image_slice.copy()

    # Convert to RGB
    rgb = np.stack([img_u8, img_u8, img_u8], axis=-1)  # (H, W, 3)

    # Apply mask overlay
    if mask_slice is not None and mask_slice.any():
        overlay = rgb.astype(np.float32)
        mc = np.array(mask_color, dtype=np.float32)
        for c in range(3):
            overlay[:, :, c] = np.where(
                mask_slice.astype(bool),
                (1 - alpha) * rgb[:, :, c] + alpha * mc[c],
                rgb[:, :, c],
            )
        rgb = overlay.clip(0, 255).astype(np.uint8)

    # Draw prompts
    if prompts:
        from PIL import ImageDraw
        pil_img = Image.fromarray(rgb)
        draw = ImageDraw.Draw(pil_img)
        for p in prompts:
            if p.get("type") == "box":
                x1, y1, x2, y2 = p["x1"], p["y1"], p["x2"], p["y2"]
                draw.rectangle([x1, y1, x2, y2], outline=(0, 120, 255), width=2)
            elif p.get("type") == "point":
                x, y = int(p["x"]), int(p["y"])
                label = p.get("label", 1)
                color = (0, 255, 0) if label == 1 else (255, 0, 0)
                r = 5
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline="white")
        rgb = np.array(pil_img)

    Image.fromarray(rgb).save(str(out_path))
    return out_path


def save_overlay_grid(
    image_volume: np.ndarray,
    mask_volume: np.ndarray,
    out_path: str | Path,
    axis: int = 0,
    num_slices: int = 8,
    **overlay_kwargs: Any,
) -> Path:
    """Create a grid image showing N evenly-spaced overlay slices.

    Parameters
    ----------
    image_volume:
        Normalized float32 3D array (H, W, D).
    mask_volume:
        Binary uint8 3D array (H, W, D).
    out_path:
        Destination .png.
    axis:
        Volume axis to slice along.
    num_slices:
        How many evenly-spaced slices to show.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = image_volume.shape[axis]
    indices = np.linspace(0, n - 1, num_slices, dtype=int)

    fig, axes = plt.subplots(2, (num_slices + 1) // 2, figsize=(4 * ((num_slices + 1) // 2), 8))
    axes = axes.flatten()

    from .nifti_utils import get_slice as _get_sl

    for i, idx in enumerate(indices):
        img_sl = _get_sl(image_volume, idx, axis)
        msk_sl = _get_sl(mask_volume, idx, axis)

        axes[i].imshow(img_sl, cmap="gray", vmin=0, vmax=1)
        if msk_sl.any():
            axes[i].imshow(
                np.ma.masked_where(msk_sl == 0, msk_sl),
                cmap="autumn",
                alpha=overlay_kwargs.get("alpha", 0.4),
            )
        axes[i].set_title(f"Slice {idx}", fontsize=9)
        axes[i].axis("off")

    # Hide unused axes
    for j in range(i + 1, len(axes)):
        axes[j].axis("off")

    plt.tight_layout()
    plt.savefig(str(out_path), dpi=100, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ─── Prompt & metrics writers ────────────────────────────────────────────────


def save_prompts_json(prompts_data: Dict[str, Any], out_path: str | Path) -> Path:
    """Serialize prompt history to JSON."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, indent=2, default=_json_default)
    return out_path


def save_metrics_json(metrics: Dict[str, Any], out_path: str | Path) -> Path:
    """Save evaluation metrics to JSON (and optionally CSV)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "computed_at": datetime.utcnow().isoformat(),
        **metrics,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)

    # Also write a CSV for easy spreadsheet import
    csv_path = out_path.with_suffix(".csv")
    try:
        import csv
        flat = {k: v for k, v in payload.items() if not isinstance(v, (dict, list))}
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            writer = csv.DictWriter(cf, fieldnames=list(flat.keys()))
            writer.writeheader()
            writer.writerow(flat)
    except Exception:
        pass  # CSV is optional

    return out_path


# ─── Private helpers ─────────────────────────────────────────────────────────


def _json_default(obj: Any) -> Any:
    """JSON serializer for numpy types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
