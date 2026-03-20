"""
Standard SAM adapter (not fine-tuned on medical images).

Can serve as a fallback when MedSAM weights are unavailable, or as a
comparative baseline.  Uses SAM's SamPredictor API which supports box,
point, and mask prompts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

from .base_adapter import BaseSegAdapter, Prompt, SegResult

_MODEL_CACHE: Dict[str, Any] = {}


class SAMAdapter(BaseSegAdapter):
    """Adapter for vanilla SAM (ViT-B/L/H) via SamPredictor.

    Supports box, point, and combined box+point prompts.
    """

    def __init__(
        self,
        device: str = "cuda",
        model_type: str = "vit_b",
        segment_anything_path: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(device=device, **kwargs)
        self.model_type = model_type
        self._predictor: Any = None
        self._segment_anything_path = segment_anything_path or os.environ.get(
            "SEGMENT_ANYTHING_PATH", ""
        )

    def load_model(
        self,
        checkpoint: str,
        segment_anything_path: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        checkpoint = str(checkpoint)
        sa_path = segment_anything_path or self._segment_anything_path

        cache_key = f"{checkpoint}_{self.device}_{self.model_type}"
        if cache_key in _MODEL_CACHE:
            self._predictor = _MODEL_CACHE[cache_key]
            self._loaded = True
            return

        if sa_path and sa_path not in sys.path:
            sys.path.insert(0, str(sa_path))

        try:
            from segment_anything import sam_model_registry, SamPredictor  # type: ignore
        except ImportError as e:
            raise ImportError(
                "segment_anything package not found."
            ) from e

        if not Path(checkpoint).exists():
            raise FileNotFoundError(f"SAM checkpoint not found: {checkpoint}")

        device = torch.device(self.device if torch.cuda.is_available() else "cpu")
        sam = sam_model_registry[self.model_type](checkpoint=checkpoint)
        sam = sam.to(device)
        sam.eval()

        predictor = SamPredictor(sam)
        _MODEL_CACHE[cache_key] = predictor
        self._predictor = predictor
        self._loaded = True

    def predict_slice(
        self,
        image_slice: np.ndarray,
        prompt: Prompt,
    ) -> SegResult:
        """Segment using SAM's predictor API."""
        self._require_loaded()

        H, W = image_slice.shape[:2]
        # SAM expects uint8 RGB
        img_u8 = (np.clip(image_slice, 0, 1) * 255).astype(np.uint8)
        img_rgb = np.stack([img_u8, img_u8, img_u8], axis=-1)

        self._predictor.set_image(img_rgb)

        box_np = None
        point_coords = None
        point_labels = None

        if prompt.box is not None:
            box_np = np.array(prompt.box, dtype=np.float32)

        if prompt.points is not None and len(prompt.points) > 0:
            coords = [(p[0], p[1]) for p in prompt.points]
            labels = [p[2] for p in prompt.points]
            point_coords = np.array(coords, dtype=np.float32)
            point_labels = np.array(labels, dtype=np.int64)

        masks, scores, _ = self._predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            box=box_np,
            multimask_output=False,
        )

        best_mask = masks[0].astype(np.uint8)
        confidence = float(scores[0]) if len(scores) > 0 else None

        return SegResult(
            slice_idx=prompt.slice_idx,
            mask=best_mask,
            confidence=confidence,
        )
