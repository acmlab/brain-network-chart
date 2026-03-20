"""
MedSAM adapter: wraps the MedSAM ViT-B model for interactive segmentation.

MedSAM (Ma et al., 2024) fine-tunes SAM on medical images and accepts
bounding-box prompts.  This adapter re-implements the inference path from
MedSAM_Inference.py in a clean, reusable class.

Reference: https://github.com/bowang-lab/MedSAM
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F

from .base_adapter import BaseSegAdapter, Prompt, SegResult

# ─── Module-level model cache (single instance per process) ──────────────────
_MODEL_CACHE: Dict[str, Any] = {}


class MedSAMAdapter(BaseSegAdapter):
    """Adapter wrapping MedSAM ViT-B for box-prompted slice segmentation.

    Usage
    -----
    >>> adapter = MedSAMAdapter(device="cuda")
    >>> adapter.load_model("/path/to/medsam_vit_b.pth",
    ...                    segment_anything_path="/path/to/MedSAM_COPY")
    >>> result = adapter.predict_slice(slice_img, prompt)
    """

    # Size MedSAM expects
    IMG_SIZE: int = 1024

    def __init__(
        self,
        device: str = "cuda",
        segment_anything_path: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(device=device, **kwargs)
        self._model: Any = None
        self._segment_anything_path = segment_anything_path or os.environ.get(
            "SEGMENT_ANYTHING_PATH", ""
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def load_model(
        self,
        checkpoint: str,
        segment_anything_path: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Load MedSAM weights.

        Parameters
        ----------
        checkpoint:
            Path to medsam_vit_b.pth.
        segment_anything_path:
            Root of the MedSAM source tree (containing segment_anything/).
            Required if segment_anything is not installed as a package.
        """
        checkpoint = str(checkpoint)
        sa_path = segment_anything_path or self._segment_anything_path

        # Check cache first
        cache_key = f"{checkpoint}_{self.device}"
        if cache_key in _MODEL_CACHE:
            self._model = _MODEL_CACHE[cache_key]
            self._loaded = True
            return

        # Inject source path so we can import segment_anything
        if sa_path and sa_path not in sys.path:
            sys.path.insert(0, str(sa_path))

        try:
            from segment_anything import sam_model_registry  # type: ignore
        except ImportError as e:
            raise ImportError(
                "segment_anything package not found. "
                "Set SEGMENT_ANYTHING_PATH in .env or config to the MedSAM source directory."
            ) from e

        if not Path(checkpoint).exists():
            raise FileNotFoundError(
                f"MedSAM checkpoint not found: {checkpoint}\n"
                "Download from: https://drive.google.com/file/d/1UAmWL88roYR7wKlnApw5Bcuzns2Mu3dF"
            )

        # Determine device
        device = _resolve_device(self.device)

        model = sam_model_registry["vit_b"](checkpoint=checkpoint)
        model = model.to(device)
        model.eval()

        _MODEL_CACHE[cache_key] = model
        self._model = model
        self.device = str(device)
        self._loaded = True

    # ── Core inference ────────────────────────────────────────────────────

    def predict_slice(
        self,
        image_slice: np.ndarray,
        prompt: Prompt,
    ) -> SegResult:
        """Segment a 2D slice using a bounding-box prompt.

        Parameters
        ----------
        image_slice:
            Float32 normalized [0,1] slice (H, W).
        prompt:
            Must have prompt_type="box" and a valid box [x1,y1,x2,y2].

        Returns
        -------
        SegResult with binary mask (H, W), logits, confidence.
        """
        self._require_loaded()

        if prompt.box is None:
            raise ValueError("MedSAMAdapter requires a bounding-box prompt.")

        device = next(self._model.parameters()).device
        H, W = image_slice.shape[:2]

        # ── Preprocess image → (1, 3, 1024, 1024) ──────────────────────
        img_3c = _slice_to_3ch_tensor(image_slice, self.IMG_SIZE)
        img_tensor = img_3c.to(device)

        # ── Scale box to 1024 space ─────────────────────────────────────
        x1, y1, x2, y2 = prompt.box
        box_1024 = np.array(
            [x1 / W * self.IMG_SIZE, y1 / H * self.IMG_SIZE,
             x2 / W * self.IMG_SIZE, y2 / H * self.IMG_SIZE],
            dtype=np.float32,
        )[None, :]  # (1, 4)

        # ── Inference ────────────────────────────────────────────────────
        with torch.no_grad():
            img_embed = self._model.image_encoder(img_tensor)
            mask, logits = _medsam_decode(self._model, img_embed, box_1024, H, W)

        mask_np = mask.cpu().numpy().squeeze().astype(np.uint8)   # (H, W)
        logits_np = logits.cpu().numpy().squeeze()                 # (H, W)

        confidence = float(torch.sigmoid(torch.tensor(logits_np)).mean())

        return SegResult(
            slice_idx=prompt.slice_idx,
            mask=mask_np,
            logits=logits_np,
            confidence=confidence,
        )

    def predict_volume(
        self,
        image_volume: np.ndarray,
        prompts: List[Prompt],
        axis: int = 0,
    ) -> np.ndarray:
        """Batch inference over all prompted slices (base class default)."""
        return super().predict_volume(image_volume, prompts, axis=axis)

    def refine_with_prompts(
        self,
        image_slice: np.ndarray,
        existing_mask: np.ndarray,
        new_prompt: Prompt,
    ) -> SegResult:
        """Re-run predict_slice with the updated prompt.

        MedSAM does not support mask-conditioned refinement natively in this
        implementation. Future work: pass logits as mask input to decoder.
        """
        return self.predict_slice(image_slice, new_prompt)


# ─── Private helpers ──────────────────────────────────────────────────────────


def _resolve_device(device_str: str) -> torch.device:
    """Resolve device string, falling back to CPU if CUDA unavailable."""
    if "cuda" in device_str and not torch.cuda.is_available():
        import warnings
        warnings.warn("CUDA not available, falling back to CPU.", stacklevel=2)
        return torch.device("cpu")
    try:
        return torch.device(device_str)
    except Exception:
        return torch.device("cpu")


def _slice_to_3ch_tensor(
    image_slice: np.ndarray,
    target_size: int = 1024,
) -> torch.Tensor:
    """Convert a 2D [0,1] float slice to (1, 3, target_size, target_size) tensor."""
    from skimage.transform import resize

    # Resize to target
    img_r = resize(
        image_slice, (target_size, target_size),
        order=3, preserve_range=True, anti_aliasing=True
    ).astype(np.float32)

    # Stack to 3 channels
    img_3c = np.stack([img_r, img_r, img_r], axis=0)  # (3, H, W)
    tensor = torch.from_numpy(img_3c).unsqueeze(0)     # (1, 3, H, W)
    return tensor


@torch.no_grad()
def _medsam_decode(
    model: Any,
    img_embed: torch.Tensor,
    box_1024: np.ndarray,
    H: int,
    W: int,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Run MedSAM prompt encoder + mask decoder, resize output to (H, W)."""
    box_torch = torch.as_tensor(
        box_1024, dtype=torch.float, device=img_embed.device
    )
    if box_torch.ndim == 2:
        box_torch = box_torch[:, None, :]  # (B, 1, 4)

    sparse_emb, dense_emb = model.prompt_encoder(
        points=None, boxes=box_torch, masks=None
    )
    low_res_logits, _ = model.mask_decoder(
        image_embeddings=img_embed,
        image_pe=model.prompt_encoder.get_dense_pe(),
        sparse_prompt_embeddings=sparse_emb,
        dense_prompt_embeddings=dense_emb,
        multimask_output=False,
    )
    # low_res_logits: (1, 1, 256, 256)
    low_res_pred = torch.sigmoid(low_res_logits)
    low_res_pred = F.interpolate(
        low_res_pred,
        size=(H, W),
        mode="bilinear",
        align_corners=False,
    )
    # Threshold at 0.5
    mask = (low_res_pred > 0.5).byte()
    return mask, low_res_pred
