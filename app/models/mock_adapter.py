"""
Mock adapter for testing and demonstration without GPU/model weights.

Generates synthetic elliptical segmentation masks based on the bounding-box
prompt.  Useful for UI development, CI tests, and offline demos.
"""

from __future__ import annotations

from typing import Any, List, Optional

import numpy as np
from skimage.draw import ellipse

from .base_adapter import BaseSegAdapter, Prompt, SegResult


class MockAdapter(BaseSegAdapter):
    """Returns a synthetic mask without any model inference.

    The mask is an ellipse fitted to the provided bounding box, optionally
    with Gaussian noise on the boundary to simulate realistic predictions.
    """

    def __init__(self, device: str = "cpu", noise: float = 0.05, **kwargs: Any):
        super().__init__(device=device, **kwargs)
        self.noise = noise

    def load_model(self, checkpoint: str = "", **kwargs: Any) -> None:
        """No-op: mock adapter needs no weights."""
        self._loaded = True

    def predict_slice(
        self,
        image_slice: np.ndarray,
        prompt: Prompt,
    ) -> SegResult:
        """Generate an elliptical mask from the bounding-box prompt."""
        H, W = image_slice.shape[:2]
        mask = np.zeros((H, W), dtype=np.uint8)

        if prompt.box is not None:
            x1, y1, x2, y2 = [int(v) for v in prompt.box]
            cx = (y1 + y2) // 2
            cy = (x1 + x2) // 2
            r_r = max(1, (y2 - y1) // 2)
            r_c = max(1, (x2 - x1) // 2)
            rr, cc = ellipse(cx, cy, r_r, r_c, shape=(H, W))
            mask[rr, cc] = 1

        elif prompt.points:
            # Tiny disk around each foreground point
            for x, y, label in prompt.points:
                if label == 1:
                    rr, cc = ellipse(int(y), int(x), 10, 10, shape=(H, W))
                    mask[rr, cc] = 1

        return SegResult(
            slice_idx=prompt.slice_idx,
            mask=mask,
            confidence=0.85,
            meta={"backend": "mock"},
        )
