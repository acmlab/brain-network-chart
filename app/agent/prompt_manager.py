"""
PromptManager: stores and organizes user-provided prompts across slices.

Prompts are keyed by (axis, slice_idx) so multiple prompts on the same
slice are supported.  Provides serialization to/from JSON for session
persistence.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.base_adapter import Prompt


PromptKey = Tuple[int, int]  # (axis, slice_idx)


class PromptManager:
    """Manages the collection of user prompts for a single segmentation session.

    Attributes
    ----------
    organ:
        Target organ / structure name (e.g. "right kidney").
    axis:
        Primary viewing axis (0=axial, 1=coronal, 2=sagittal).
    _prompts:
        Internal dict mapping (axis, slice_idx) → list of Prompt objects.
    history:
        Ordered list of (timestamp, action, details) for audit trail.
    """

    def __init__(self, organ: str = "custom", axis: int = 0):
        self.organ = organ
        self.axis = axis
        self._prompts: Dict[PromptKey, List[Prompt]] = defaultdict(list)
        self.history: List[Dict[str, Any]] = []

    # ── Prompt CRUD ──────────────────────────────────────────────────────────

    def add_box(
        self,
        slice_idx: int,
        box: List[float],
        axis: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Prompt:
        """Add a bounding-box prompt on *slice_idx*.

        Parameters
        ----------
        slice_idx:
            Slice index in the volume.
        box:
            [x1, y1, x2, y2] in pixel coordinates of the slice.
        axis:
            Overrides the manager's default axis if provided.
        meta:
            Optional extra metadata.

        Returns
        -------
        The created Prompt object.
        """
        ax = axis if axis is not None else self.axis
        p = Prompt(
            slice_idx=slice_idx,
            axis=ax,
            prompt_type="box",
            box=box,
            meta={
                "organ": self.organ,
                "timestamp": datetime.utcnow().isoformat(),
                **(meta or {}),
            },
        )
        key: PromptKey = (ax, slice_idx)
        self._prompts[key].append(p)
        self._log("add_box", {"slice_idx": slice_idx, "box": box, "axis": ax})
        return p

    def add_point(
        self,
        slice_idx: int,
        x: float,
        y: float,
        label: int = 1,
        axis: Optional[int] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Prompt:
        """Add a point prompt (foreground label=1, background label=0)."""
        ax = axis if axis is not None else self.axis
        key: PromptKey = (ax, slice_idx)

        # Append point to existing prompt on this slice if present, else create new
        existing = [p for p in self._prompts[key] if p.prompt_type == "point"]
        if existing:
            p = existing[-1]
            if p.points is None:
                p.points = []
            p.points.append((x, y, label))
        else:
            p = Prompt(
                slice_idx=slice_idx,
                axis=ax,
                prompt_type="point",
                points=[(x, y, label)],
                meta={
                    "organ": self.organ,
                    "timestamp": datetime.utcnow().isoformat(),
                    **(meta or {}),
                },
            )
            self._prompts[key].append(p)

        self._log("add_point", {"slice_idx": slice_idx, "x": x, "y": y, "label": label})
        return p

    def remove_slice(self, slice_idx: int, axis: Optional[int] = None) -> None:
        """Remove all prompts for a given slice."""
        ax = axis if axis is not None else self.axis
        key: PromptKey = (ax, slice_idx)
        if key in self._prompts:
            del self._prompts[key]
            self._log("remove_slice", {"slice_idx": slice_idx})

    def clear_all(self) -> None:
        """Remove all prompts."""
        self._prompts.clear()
        self._log("clear_all", {})

    # ── Accessors ────────────────────────────────────────────────────────────

    def get_prompts_for_slice(
        self,
        slice_idx: int,
        axis: Optional[int] = None,
    ) -> List[Prompt]:
        ax = axis if axis is not None else self.axis
        return list(self._prompts.get((ax, slice_idx), []))

    def get_all_prompts(self, axis: Optional[int] = None) -> List[Prompt]:
        """Return all prompts (optionally filtered by axis)."""
        ax = axis if axis is not None else self.axis
        out: List[Prompt] = []
        for (a, _), prompts in self._prompts.items():
            if a == ax:
                out.extend(prompts)
        return out

    def prompted_slices(self, axis: Optional[int] = None) -> List[int]:
        """Return sorted list of slice indices that have prompts."""
        ax = axis if axis is not None else self.axis
        return sorted({s for (a, s) in self._prompts.keys() if a == ax})

    def has_prompts(self) -> bool:
        return bool(self._prompts)

    def num_prompted_slices(self) -> int:
        return len({s for (_, s) in self._prompts.keys()})

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        prompts_list = []
        for key, prompts in self._prompts.items():
            for p in prompts:
                prompts_list.append(p.to_dict())
        return {
            "organ": self.organ,
            "axis": self.axis,
            "prompts": prompts_list,
            "history": self.history,
        }

    def save(self, path: str | Path) -> None:
        """Save prompts to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptManager":
        """Restore from a serialized dict."""
        pm = cls(organ=data.get("organ", "custom"), axis=data.get("axis", 0))
        for pdata in data.get("prompts", []):
            p = Prompt(
                slice_idx=pdata["slice_idx"],
                axis=pdata.get("axis", pm.axis),
                prompt_type=pdata.get("prompt_type", "box"),
                box=pdata.get("box"),
                points=[tuple(pt) for pt in pdata.get("points", [])] or None,
                meta=pdata.get("meta", {}),
            )
            key: PromptKey = (p.axis, p.slice_idx)
            pm._prompts[key].append(p)
        pm.history = data.get("history", [])
        return pm

    @classmethod
    def load(cls, path: str | Path) -> "PromptManager":
        """Load from a JSON file saved by .save()."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # ── Private ──────────────────────────────────────────────────────────────

    def _log(self, action: str, details: Dict[str, Any]) -> None:
        self.history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                **details,
            }
        )
