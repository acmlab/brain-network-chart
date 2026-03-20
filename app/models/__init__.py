"""Model adapter registry and loader."""

from .base_adapter import BaseSegAdapter, Prompt, SegResult
from .medsam_adapter import MedSAMAdapter
from .medsam2_adapter import MedSAM2Adapter
from .sam_adapter import SAMAdapter
from .mock_adapter import MockAdapter


def load_adapter(backend: str, **kwargs) -> BaseSegAdapter:
    """Factory: create and return the correct adapter.

    Parameters
    ----------
    backend:
        "medsam" | "medsam2" | "sam" | "mock"
    **kwargs:
        Passed to the adapter constructor (checkpoint, device, etc.)
    """
    backend = backend.lower()
    if backend == "medsam":
        return MedSAMAdapter(**kwargs)
    elif backend == "medsam2":
        return MedSAM2Adapter(**kwargs)
    elif backend == "sam":
        return SAMAdapter(**kwargs)
    elif backend == "mock":
        return MockAdapter(**kwargs)
    else:
        raise ValueError(
            f"Unknown backend {backend!r}. Choose from: medsam, medsam2, sam, mock"
        )


__all__ = [
    "BaseSegAdapter",
    "Prompt",
    "SegResult",
    "MedSAMAdapter",
    "MedSAM2Adapter",
    "SAMAdapter",
    "MockAdapter",
    "load_adapter",
]
