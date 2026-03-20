"""
Configuration loader.

Priority order (highest to lowest):
  1. Environment variables (from shell or .env file)
  2. config/default.yaml

Usage
-----
>>> cfg = load_config()
>>> cfg["model"]["checkpoint"]
'/path/to/medsam_vit_b.pth'
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
_MEDSAM_ROOT = _HERE.parent
_DEFAULT_CFG = _MEDSAM_ROOT / "config" / "default.yaml"


def load_config(cfg_path: str | Path = _DEFAULT_CFG) -> Dict[str, Any]:
    """Load configuration from YAML, then override with env vars.

    Returns a nested dict with the merged config.
    """
    # Load .env if present
    env_path = _MEDSAM_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg: Dict[str, Any] = yaml.safe_load(f)

    # ── Environment overrides ──────────────────────────────────────────────
    _override_str(cfg, ["model", "checkpoint"], "MEDSAM_CHECKPOINT")
    _override_str(cfg, ["model", "segment_anything_path"], "SEGMENT_ANYTHING_PATH")
    _override_str(cfg, ["model", "device"], "DEVICE")
    _override_str(cfg, ["data", "root"], "DATA_ROOT")
    _override_str(cfg, ["data", "kidney_dir"], "KIDNEY_DATA_DIR")
    _override_str(cfg, ["data", "heart_dir"], "HEART_DATA_DIR")
    _override_str(cfg, ["output", "base_dir"], "OUTPUT_DIR")
    _override_int(cfg, ["ui", "port"], "GRADIO_PORT")
    _override_bool(cfg, ["ui", "share"], "GRADIO_SHARE")
    _override_str(cfg, ["logging", "level"], "LOG_LEVEL")
    _override_bool(cfg, ["output", "save_intermediates"], "SAVE_INTERMEDIATES")

    return cfg


def load_organs_config(organs_path: str | Path | None = None) -> Dict[str, Any]:
    """Load organ metadata from config/organs.yaml."""
    if organs_path is None:
        organs_path = _MEDSAM_ROOT / "config" / "organs.yaml"
    with open(organs_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("organs", {})


# ─── Private helpers ─────────────────────────────────────────────────────────


def _nested_set(d: Dict[str, Any], keys: list, value: Any) -> None:
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _nested_get(d: Dict[str, Any], keys: list) -> Any:
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _override_str(cfg: Dict[str, Any], keys: list, env_var: str) -> None:
    val = os.environ.get(env_var)
    if val is not None:
        _nested_set(cfg, keys, val)


def _override_int(cfg: Dict[str, Any], keys: list, env_var: str) -> None:
    val = os.environ.get(env_var)
    if val is not None:
        try:
            _nested_set(cfg, keys, int(val))
        except ValueError:
            pass


def _override_bool(cfg: Dict[str, Any], keys: list, env_var: str) -> None:
    val = os.environ.get(env_var)
    if val is not None:
        _nested_set(cfg, keys, val.lower() in ("1", "true", "yes"))
