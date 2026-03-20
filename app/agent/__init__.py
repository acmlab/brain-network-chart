"""Agent layer: orchestration of prompts, inference, and propagation."""

from .orchestrator import SegmentationOrchestrator
from .prompt_manager import PromptManager

__all__ = ["SegmentationOrchestrator", "PromptManager"]
