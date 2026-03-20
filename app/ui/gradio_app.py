"""
MedSAM Agent — Gradio Web UI  (Three-View Mode)

Layout
------
Top row:   File upload, organ, backend selector, Load button | Session info.
Center:    Three synchronized viewers — Axial / Coronal / Sagittal.
Controls:  Prompt panel (drag-draw box, point prompts) + action buttons.
Bottom:    Export & Evaluation accordion.

Interaction
-----------
1. Load a NIfTI file.
2. Three views appear simultaneously (Axial / Coronal / Sagittal).
3. Click any view to make it the *active* view (blue border).
4. Scroll wheel on any view to navigate that axis independently.
5. Drag on the active view to draw a bounding-box prompt (auto-added).
6. Segment / Propagate / Export as before.

Performance notes
-----------------
- Wheel callbacks use show_progress="hidden" to suppress the spinner.
- Each wheel callback only updates one image component (not all three).
- Volume is loaded once; slices are rendered on demand from the cached
  normalised volume inside NiftiReader.
"""

from __future__ import annotations

import json
import logging
import traceback
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ─── path setup ──────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_MEDSAM_ROOT = _HERE.parent.parent
if str(_MEDSAM_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEDSAM_ROOT))

import gradio as gr
from dotenv import load_dotenv

load_dotenv(dotenv_path=_MEDSAM_ROOT / ".env", override=False)

from app.config_loader import load_config
from app.models import load_adapter
from app.agent.orchestrator import SegmentationOrchestrator

logger = logging.getLogger(__name__)

_CFG = load_config()
_ADAPTER_CACHE: Dict[str, Any] = {}
_AXIS_NAMES = ["Axial", "Coronal", "Sagittal"]


# ─── Adapter loader ───────────────────────────────────────────────────────────


def _get_adapter(backend: str = "medsam") -> Any:
    if backend not in _ADAPTER_CACHE:
        cfg = _CFG
        adapter = load_adapter(
            backend,
            device=cfg["model"]["device"],
            segment_anything_path=cfg["model"].get("segment_anything_path", ""),
            medsam2_repo_path=cfg["model"].get("medsam2_repo_path", ""),
        )
        try:
            if backend in ("medsam", "sam"):
                adapter.load_model(
                    cfg["model"]["checkpoint"],
                    segment_anything_path=cfg["model"].get("segment_anything_path", ""),
                )
            elif backend == "medsam2":
                adapter.load_model(
                    cfg["model"]["medsam2_checkpoint"],
                    medsam2_repo_path=cfg["model"].get("medsam2_repo_path", ""),
                    config_file=cfg["model"].get("medsam2_config"),
                )
            else:
                adapter.load_model()
        except Exception as exc:
            logger.warning(
                f"Failed to load {backend} model: {exc}. "
                "Falling back to mock backend."
            )
            from app.models.mock_adapter import MockAdapter
            adapter = MockAdapter()
            adapter.load_model()
        _ADAPTER_CACHE[backend] = adapter
    return _ADAPTER_CACHE[backend]


# ─── State helpers ────────────────────────────────────────────────────────────


def _get_orch(state: Dict[str, Any]) -> Optional[SegmentationOrchestrator]:
    return state.get("orch")


def _require_orch(state: Dict[str, Any]) -> SegmentationOrchestrator:
    orch = _get_orch(state)
    if orch is None:
        raise gr.Error("No volume loaded. Please load a NIfTI file first.")
    return orch


def _active_idx(active_axis: Any, idx_ax: Any, idx_cor: Any, idx_sag: Any) -> Tuple[int, int]:
    """Return (axis, slice_idx) for the currently active view."""
    axis = int(active_axis)
    return axis, [int(idx_ax), int(idx_cor), int(idx_sag)][axis]


# ─── Rendering ────────────────────────────────────────────────────────────────


def _render_slice(
    orch: SegmentationOrchestrator,
    slice_idx: int,
    axis: int,
    show_mask: bool = True,
) -> np.ndarray:
    """Return an RGB uint8 numpy array for one slice."""
    try:
        if show_mask:
            return orch.get_slice_overlay(slice_idx, axis=axis)
        img = orch.get_slice_image(slice_idx, axis=axis)
        img_u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        return np.stack([img_u8, img_u8, img_u8], axis=-1)
    except Exception:
        return np.zeros((64, 64, 3), dtype=np.uint8)


def _render_all(
    orch: SegmentationOrchestrator,
    idx_ax: int,
    idx_cor: int,
    idx_sag: int,
    show_mask: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        _render_slice(orch, idx_ax, 0, show_mask),
        _render_slice(orch, idx_cor, 1, show_mask),
        _render_slice(orch, idx_sag, 2, show_mask),
    )


# ─── Info formatters ──────────────────────────────────────────────────────────


def _view_label(axis: int, idx: int, orch: Optional[SegmentationOrchestrator]) -> str:
    n = orch.reader.num_slices(axis=axis) - 1 if (orch and orch.reader) else "?"
    return f"**{_AXIS_NAMES[axis]}** — {idx} / {n}"


def _fmt_info(state: Dict[str, Any]) -> str:
    orch = _get_orch(state)
    if orch is None:
        return "No volume loaded."
    organ = state.get("organ", "?")
    active = state.get("active_axis", 0)
    idxs = [state.get(f"idx_{a}", 0) for a in range(3)]
    prompted = orch.prompt_manager.num_prompted_slices() if orch.prompt_manager else 0
    has_gt = orch.session.has_gt if orch.session else False
    gt_str = "GT loaded" if has_gt else "No GT (inference-only)"
    return (
        f"Organ: {organ} | Shape: {orch.reader.shape}\n"
        f"Active: {_AXIS_NAMES[active]} | "
        f"Ax:{idxs[0]}  Cor:{idxs[1]}  Sag:{idxs[2]}\n"
        f"Prompted slices: {prompted} | {gt_str}"
    )


def _load_gt_mask(path: str) -> np.ndarray:
    from app.io import nifti_utils as _nu
    vol, _, _ = _nu.load_nifti(path)
    return vol.astype(np.uint8)


# ═══════════════════════════════════════════════════════════════════════════════
# Three-view JavaScript
# ═══════════════════════════════════════════════════════════════════════════════

_TRIVIEW_JS = """
() => {
    /* ── constants ─────────────────────────────────────────────────────── */
    const VIEWS = [
        { id: 'viewer-ax',  idxId: 'idx-ax',  maxId: 'max-ax',  axis: 0 },
        { id: 'viewer-cor', idxId: 'idx-cor', maxId: 'max-cor', axis: 1 },
        { id: 'viewer-sag', idxId: 'idx-sag', maxId: 'max-sag', axis: 2 },
    ];
    let activeAxis = 0;
    let drawCvs = null, drawImg = null;

    /* ── Gradio input helpers ───────────────────────────────────────────── */
    /* Find the actual <input> or <textarea> inside a Gradio component div. */
    function findInput(eid) {
        const c = document.querySelector('#' + eid);
        if (!c) {
            console.warn('[triview] DOM element not found:', eid);
            return null;
        }
        return (c.querySelector('input[type="number"]')
             || c.querySelector('input[type="text"]')
             || c.querySelector('input')
             || c.querySelector('textarea'));
    }

    /* Write a value and fire input + change + blur so Gradio picks it up. */
    function setVal(el, v) {
        if (!el) return;
        const isTA = el.tagName === 'TEXTAREA';
        const proto = isTA ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (setter) {
            setter.call(el, String(v));
            el.dispatchEvent(new Event('input',  { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur',   { bubbles: true }));
        }
    }

    /* ── Active-view visual indicator ──────────────────────────────────── */
    function markActive(axis) {
        VIEWS.forEach(v => {
            const c = document.querySelector('#' + v.id);
            if (!c) return;
            if (v.axis === axis) {
                c.style.outline = '3px solid #0088ff';
                c.style.outlineOffset = '-3px';
                c.style.borderRadius = '4px';
            } else {
                c.style.outline = 'none';
            }
        });
    }

    /* ── Wheel listener ─────────────────────────────────────────────────── */
    function addWheel(container, view) {
        function doWheel(e) {
            e.preventDefault();
            const idxEl = findInput(view.idxId);
            const maxEl = findInput(view.maxId);
            const cur = parseInt(idxEl?.value) || 0;
            const mx  = parseInt(maxEl?.value)  || 0;
            const nv  = Math.max(0, Math.min(mx, cur + (e.deltaY > 0 ? 1 : -1)));
            console.log('[wheel]', { axis: view.axis, cur, nv, foundIdx: !!idxEl, foundMax: !!maxEl });
            if (!idxEl) return;
            if (nv !== cur) setVal(idxEl, nv);
        }
        container.addEventListener('wheel', doWheel, { passive: false });
    }

    /* ── Draw-box canvas on active view ─────────────────────────────────── */
    function initDrawCanvas() {
        if (drawCvs && drawCvs.parentNode) drawCvs.remove();
        drawCvs = null; drawImg = null;

        const view = VIEWS[activeAxis];
        const container = document.querySelector('#' + view.id);
        if (!container) return;
        const img = container.querySelector('img');
        if (!img) { setTimeout(initDrawCanvas, 300); return; }
        drawImg = img;

        drawCvs = document.createElement('canvas');
        drawCvs.style.cssText =
            'position:absolute;z-index:10;cursor:crosshair;pointer-events:auto;';
        const wrap = img.parentElement;
        wrap.style.position = 'relative';
        wrap.appendChild(drawCvs);

        function sync() {
            if (!drawCvs || !img.parentNode) return;
            drawCvs.width  = img.clientWidth;
            drawCvs.height = img.clientHeight;
            drawCvs.style.top  = img.offsetTop  + 'px';
            drawCvs.style.left = img.offsetLeft + 'px';
        }
        new ResizeObserver(sync).observe(img);
        img.addEventListener('load', sync);
        sync();

        /* Clear box overlay when image src changes (slice navigation) */
        new MutationObserver(() => {
            if (drawCvs) {
                drawCvs.getContext('2d').clearRect(0, 0, drawCvs.width, drawCvs.height);
                sync();
            }
        }).observe(img, { attributes: true, attributeFilter: ['src'] });

        /* Forward wheel events from canvas to the hidden index input */
        drawCvs.addEventListener('wheel', (e) => {
            e.preventDefault();
            const idxEl = findInput(view.idxId);
            const maxEl = findInput(view.maxId);
            const cur = parseInt(idxEl?.value) || 0;
            const mx  = parseInt(maxEl?.value)  || 0;
            const nv  = Math.max(0, Math.min(mx, cur + (e.deltaY > 0 ? 1 : -1)));
            console.log('[wheel-canvas]', { axis: view.axis, cur, nv, foundIdx: !!idxEl });
            if (!idxEl) return;
            if (nv !== cur) setVal(idxEl, nv);
        }, { passive: false });

        /* Drag-to-draw bounding box */
        let sx = 0, sy = 0, drawing = false;

        drawCvs.onmousedown = e => {
            if (e.button !== 0) return;
            e.preventDefault(); e.stopPropagation();
            const b = drawCvs.getBoundingClientRect();
            sx = e.clientX - b.left; sy = e.clientY - b.top;
            drawing = true;
        };

        drawCvs.onmousemove = e => {
            if (!drawing) return;
            const b = drawCvs.getBoundingClientRect();
            const cx = e.clientX - b.left, cy = e.clientY - b.top;
            const ctx = drawCvs.getContext('2d');
            ctx.clearRect(0, 0, drawCvs.width, drawCvs.height);
            ctx.strokeStyle = '#00aaff'; ctx.lineWidth = 2;
            ctx.setLineDash([6, 3]);
            ctx.strokeRect(sx, sy, cx - sx, cy - sy);
        };

        /* Cancel drag if mouse leaves the canvas */
        drawCvs.onmouseleave = () => {
            if (drawing) {
                drawing = false;
                drawCvs.getContext('2d').clearRect(0, 0, drawCvs.width, drawCvs.height);
            }
        };

        drawCvs.onmouseup = e => {
            if (!drawing) return;
            drawing = false;
            const b = drawCvs.getBoundingClientRect();
            const ex = e.clientX - b.left, ey = e.clientY - b.top;
            if (Math.abs(ex - sx) < 5 && Math.abs(ey - sy) < 5) return;

            /* Map display coords → image pixel coords */
            const nw = img.naturalWidth, nh = img.naturalHeight;
            const cw = drawCvs.width,    ch = drawCvs.height;
            if (!nw || !nh) return;
            const sc = Math.min(cw / nw, ch / nh);
            const ox = (cw - nw * sc) / 2, oy = (ch - nh * sc) / 2;
            function toPx(dx, dy) {
                return {
                    x: Math.max(0, Math.min(nw, Math.round((dx - ox) / sc))),
                    y: Math.max(0, Math.min(nh, Math.round((dy - oy) / sc)))
                };
            }
            const p1 = toPx(Math.min(sx, ex), Math.min(sy, ey));
            const p2 = toPx(Math.max(sx, ex), Math.max(sy, ey));

            /* Draw final green box */
            const ctx = drawCvs.getContext('2d');
            ctx.clearRect(0, 0, drawCvs.width, drawCvs.height);
            ctx.strokeStyle = '#00ff44'; ctx.lineWidth = 2; ctx.setLineDash([]);
            const dx1 = Math.min(sx, ex), dy1 = Math.min(sy, ey);
            ctx.strokeRect(dx1, dy1, Math.abs(ex - sx), Math.abs(ey - sy));
            ctx.fillStyle = '#00ff44';
            [[dx1, dy1],[dx1+Math.abs(ex-sx),dy1],
             [dx1, dy1+Math.abs(ey-sy)],[dx1+Math.abs(ex-sx),dy1+Math.abs(ey-sy)]]
                .forEach(([cx,cy]) => ctx.fillRect(cx-3, cy-3, 6, 6));

            /* Send coords to Python */
            const el = findInput('box-coords-hidden')
                    || document.querySelector('#box-coords-hidden textarea');
            const payload = { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y,
                              axis: activeAxis, _t: Date.now() };
            console.log('[box]', { ...payload, foundEl: !!el });
            if (el) setVal(el, JSON.stringify(payload));
        };
    }

    /* ── Activate a view ────────────────────────────────────────────────── */
    function setActive(axis) {
        if (activeAxis === axis) return;
        activeAxis = axis;
        markActive(axis);
        const el = findInput('active-view');
        if (el) setVal(el, axis);
        initDrawCanvas();
    }

    /* ── Main init (retries until DOM is ready) ─────────────────────────── */
    function init() {
        let ready = true;
        VIEWS.forEach(v => {
            const c = document.querySelector('#' + v.id);
            if (!c) { ready = false; return; }
            if (c.dataset.triviewInit) return;
            c.dataset.triviewInit = '1';
            addWheel(c, v);
            /* Click on any non-active view activates it */
            c.addEventListener('mousedown', e => {
                if (e.button === 0 && activeAxis !== v.axis) setActive(v.axis);
            });
        });
        if (!ready) { setTimeout(init, 500); return; }

        markActive(0);
        initDrawCanvas();

        /* Watch for img element replacement inside each viewer */
        VIEWS.forEach(v => {
            const c = document.querySelector('#' + v.id);
            if (!c) return;
            new MutationObserver(() => {
                if (v.axis === activeAxis && drawImg && !c.contains(drawImg)) {
                    setTimeout(initDrawCanvas, 150);
                }
            }).observe(c, { childList: true, subtree: true });
        });
    }

    setTimeout(init, 1000);
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Event handlers
# ═══════════════════════════════════════════════════════════════════════════════


def handle_load_volume(
    file_obj: Any,
    organ: str,
    backend: str,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Load NIfTI, render all three views, return initial state."""
    if file_obj is None:
        return (state,) + (None,) * 3 + ("",) * 3 + (0,) * 6 + (
            "Upload a NIfTI file first.", "No volume loaded."
        )
    try:
        path = file_obj if isinstance(file_obj, str) else file_obj.name
        adapter = _get_adapter(backend)
        cfg = _CFG

        orch = SegmentationOrchestrator(
            adapter=adapter,
            output_dir=cfg["output"]["base_dir"],
            propagation_strategy=cfg["propagation"]["strategy"],
            save_intermediates=cfg["output"]["save_intermediates"],
        )
        orch.new_session(
            volume_path=path,
            organ=organ,
            axis=0,
            norm_method=cfg["data"]["intensity"]["mr"]["method"],
        )

        n = [orch.reader.num_slices(axis=a) for a in range(3)]
        mid = [nv // 2 for nv in n]

        state.update({
            "orch": orch,
            "organ": organ,
            "backend": backend,
            "active_axis": 0,
            "idx_0": mid[0],
            "idx_1": mid[1],
            "idx_2": mid[2],
        })

        imgs = _render_all(orch, mid[0], mid[1], mid[2], show_mask=False)
        lbls = [_view_label(a, mid[a], orch) for a in range(3)]
        log = (
            f"Loaded: {Path(path).name}\n"
            f"Shape: {orch.reader.shape} | Backend: {backend} | Organ: {organ}"
        )
        return (
            state,
            *imgs,
            *lbls,
            mid[0], mid[1], mid[2],          # idx values
            n[0] - 1, n[1] - 1, n[2] - 1,   # max values
            log,
            _fmt_info(state),
        )
    except Exception as exc:
        tb = traceback.format_exc()
        return (state,) + (None,) * 3 + ("",) * 3 + (0,) * 6 + (
            f"Error loading volume:\n{exc}\n\n{tb}", "No volume loaded."
        )


# ── Per-axis wheel handlers (show_progress="hidden" keeps them fast) ──────────


def handle_wheel_ax(idx: int, show_mask: bool, state: Dict[str, Any]):
    logger.info(f"WHEEL_AX -> idx={idx}")
    orch = _get_orch(state)
    if not orch:
        return gr.update(), gr.update()
    si = int(idx)
    state["idx_0"] = si
    return _render_slice(orch, si, 0, show_mask), _view_label(0, si, orch)


def handle_wheel_cor(idx: int, show_mask: bool, state: Dict[str, Any]):
    logger.info(f"WHEEL_COR -> idx={idx}")
    orch = _get_orch(state)
    if not orch:
        return gr.update(), gr.update()
    si = int(idx)
    state["idx_1"] = si
    return _render_slice(orch, si, 1, show_mask), _view_label(1, si, orch)


def handle_wheel_sag(idx: int, show_mask: bool, state: Dict[str, Any]):
    logger.info(f"WHEEL_SAG -> idx={idx}")
    orch = _get_orch(state)
    if not orch:
        return gr.update(), gr.update()
    si = int(idx)
    state["idx_2"] = si
    return _render_slice(orch, si, 2, show_mask), _view_label(2, si, orch)


def handle_activate_view(axis_val: int, state: Dict[str, Any]) -> Dict[str, Any]:
    """Store active axis in Python state (called when JS sets active-view)."""
    logger.info(f"ACTIVATE_VIEW -> axis={axis_val}")
    state["active_axis"] = int(axis_val)
    return state


def handle_show_mask(
    idx_ax: int, idx_cor: int, idx_sag: int,
    show_mask: bool,
    state: Dict[str, Any],
) -> Tuple[Any, Any, Any]:
    orch = _get_orch(state)
    if not orch:
        return gr.update(), gr.update(), gr.update()
    return _render_all(orch, int(idx_ax), int(idx_cor), int(idx_sag), show_mask)


# ── Box prompt handlers ───────────────────────────────────────────────────────


def handle_box_drawn(
    coords_json: str,
    idx_ax: int, idx_cor: int, idx_sag: int,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Receive box drawn by JS canvas, auto-add as prompt on the active view."""
    logger.info(f"HANDLE_BOX_DRAWN: {coords_json}")
    try:
        coords = json.loads(coords_json)
        x1, y1 = int(coords["x1"]), int(coords["y1"])
        x2, y2 = int(coords["x2"]), int(coords["y2"])
        axis = int(coords.get("axis", state.get("active_axis", 0)))
    except Exception:
        return (gr.update(),) * 9

    orch = _get_orch(state)
    if not orch:
        return x1, y1, x2, y2, gr.update(), gr.update(), gr.update(), \
               "Load a volume first.", gr.update()

    si = [int(idx_ax), int(idx_cor), int(idx_sag)][axis]

    if x2 <= x1 or y2 <= y1:
        return x1, y1, x2, y2, gr.update(), gr.update(), gr.update(), \
               f"Invalid box [{x1},{y1},{x2},{y2}]", _fmt_info(state)

    try:
        orch.add_box_prompt(si, [x1, y1, x2, y2], axis=axis)
        imgs = [gr.update(), gr.update(), gr.update()]
        imgs[axis] = _render_slice(orch, si, axis, show_mask=True)
        log = (f"Box added: {_AXIS_NAMES[axis]} slice {si},"
               f" [{x1},{y1},{x2},{y2}]")
        return x1, y1, x2, y2, *imgs, log, _fmt_info(state)
    except Exception as exc:
        return x1, y1, x2, y2, gr.update(), gr.update(), gr.update(), \
               f"Error: {exc}", _fmt_info(state)


def handle_add_box(
    active_view: int,
    idx_ax: int, idx_cor: int, idx_sag: int,
    x1: float, y1: float, x2: float, y2: float,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Manual box prompt via numeric inputs."""
    try:
        orch = _require_orch(state)
        axis, si = _active_idx(active_view, idx_ax, idx_cor, idx_sag)
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

        if x2 <= x1 or y2 <= y1:
            return (gr.update(),) * 3 + (
                f"Invalid box: x1={x1},y1={y1} must be < x2={x2},y2={y2}",
                _fmt_info(state),
            )

        orch.add_box_prompt(si, [x1, y1, x2, y2], axis=axis)
        imgs = [gr.update(), gr.update(), gr.update()]
        imgs[axis] = _render_slice(orch, si, axis, show_mask=True)
        log = f"Box added: {_AXIS_NAMES[axis]} slice {si}, [{x1},{y1},{x2},{y2}]"
        return *imgs, log, _fmt_info(state)
    except gr.Error:
        raise
    except Exception as exc:
        return (gr.update(),) * 3 + (f"Error: {exc}", _fmt_info(state))


def handle_add_point(
    active_view: int,
    idx_ax: int, idx_cor: int, idx_sag: int,
    px: float, py: float, label: int,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Point prompt on the active view."""
    try:
        orch = _require_orch(state)
        axis, si = _active_idx(active_view, idx_ax, idx_cor, idx_sag)
        orch.add_point_prompt(si, px, py, label, axis=axis)
        imgs = [gr.update(), gr.update(), gr.update()]
        imgs[axis] = _render_slice(orch, si, axis, show_mask=True)
        lbl_str = "FG" if label == 1 else "BG"
        log = f"Point added: {_AXIS_NAMES[axis]} slice {si}, ({px:.0f},{py:.0f}), {lbl_str}"
        return *imgs, log, _fmt_info(state)
    except gr.Error:
        raise
    except Exception as exc:
        return (gr.update(),) * 3 + (f"Error: {exc}", _fmt_info(state))


# ── Action handlers ───────────────────────────────────────────────────────────


def handle_segment(
    active_view: int,
    idx_ax: int, idx_cor: int, idx_sag: int,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Run inference on the active view's current slice."""
    try:
        orch = _require_orch(state)
        axis, si = _active_idx(active_view, idx_ax, idx_cor, idx_sag)
        mask = orch.segment_slice(si, axis=axis)
        area = int(mask.sum())
        imgs = [gr.update(), gr.update(), gr.update()]
        imgs[axis] = _render_slice(orch, si, axis, show_mask=True)
        log = f"Segmented: {_AXIS_NAMES[axis]} slice {si}, foreground={area:,} px"
        return *imgs, log, _fmt_info(state)
    except gr.Error:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        return (gr.update(),) * 3 + (f"Error: {exc}\n{tb}", _fmt_info(state))


def handle_clear(
    active_view: int,
    idx_ax: int, idx_cor: int, idx_sag: int,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Clear prompts on the active view's current slice."""
    try:
        orch = _require_orch(state)
        axis, si = _active_idx(active_view, idx_ax, idx_cor, idx_sag)
        orch.remove_prompt(si, axis=axis)
        if orch.mask_volume is not None:
            from app.io import nifti_utils as _nu
            sl = _nu.get_slice(orch.mask_volume, si, axis)
            _nu.set_slice(orch.mask_volume, si,
                          np.zeros(sl.shape, dtype=np.uint8), axis)
        imgs = [gr.update(), gr.update(), gr.update()]
        imgs[axis] = _render_slice(orch, si, axis, show_mask=True)
        return *imgs, f"Cleared: {_AXIS_NAMES[axis]} slice {si}", _fmt_info(state)
    except gr.Error:
        raise
    except Exception as exc:
        return (gr.update(),) * 3 + (f"Error: {exc}", _fmt_info(state))


def handle_propagate(
    active_view: int,
    idx_ax: int, idx_cor: int, idx_sag: int,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    """Propagate along whichever axis has prompted slices, refresh all views."""
    try:
        orch = _require_orch(state)
        pm = orch.prompt_manager

        # Find the axis that actually has prompts.
        # Check the active view first, then the remaining axes in order.
        prop_axis = None
        for candidate in [int(active_view), 0, 1, 2]:
            if pm and pm.prompted_slices(axis=candidate):
                prop_axis = candidate
                break

        if prop_axis is None:
            return (gr.update(),) * 3 + (
                "No prompts found on any axis. "
                "Draw a box and segment at least one slice first.",
                _fmt_info(state),
            )

        pm.axis = prop_axis          # tell the orchestrator which axis to use
        mask_vol = orch.propagate_to_volume()
        total_fg = int(mask_vol.sum())
        imgs = _render_all(orch, int(idx_ax), int(idx_cor), int(idx_sag),
                           show_mask=True)
        log = (
            f"Propagation complete! axis={_AXIS_NAMES[prop_axis]}\n"
            f"  Foreground voxels: {total_fg:,}  |  shape: {mask_vol.shape}"
        )
        return *imgs, log, _fmt_info(state)
    except gr.Error:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        return (gr.update(),) * 3 + (f"Error: {exc}\n{tb}", _fmt_info(state))


def handle_export(state: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    try:
        orch = _require_orch(state)
        out = orch.save_outputs(save_mask=True, save_overlay=True, save_prompts=True)
        mask_path = str(out.get("mask", ""))
        lines = ["Outputs saved:"] + [f"  {k}: {v}" for k, v in out.items()]
        return "\n".join(lines), mask_path if mask_path else None
    except gr.Error:
        raise
    except Exception as exc:
        return f"Error: {exc}", None


def handle_load_gt(
    gt_file: Any,
    idx_ax: int, idx_cor: int, idx_sag: int,
    show_mask: bool,
    state: Dict[str, Any],
) -> Tuple[Any, ...]:
    try:
        orch = _require_orch(state)
        if gt_file is None:
            return (gr.update(),) * 3 + ("No GT file provided.", _fmt_info(state))
        gt_path = gt_file if isinstance(gt_file, str) else gt_file.name
        orch._session.gt_mask = _load_gt_mask(gt_path)
        orch._session.has_gt = True
        metrics = orch.compute_metrics()
        if metrics is None:
            lines = ["GT loaded — run segmentation first to compute metrics."]
        else:
            lines = ["Metrics:"] + [
                f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}"
                for k, v in metrics.items()
            ]
        imgs = _render_all(orch, int(idx_ax), int(idx_cor), int(idx_sag), show_mask)
        return *imgs, "\n".join(lines), _fmt_info(state)
    except Exception as exc:
        return (gr.update(),) * 3 + (f"Error: {exc}", _fmt_info(state))


# ═══════════════════════════════════════════════════════════════════════════════
# Build the Gradio app
# ═══════════════════════════════════════════════════════════════════════════════


def build_app() -> gr.Blocks:
    cfg = _CFG
    organs = cfg["agent"]["default_organs"]
    backends = ["medsam", "medsam2", "sam", "mock"]

    with gr.Blocks(title="MedSAM Agent — Three-View") as demo:

        # ── Inject CSS to hide bridge components ─────────────────────────
        gr.HTML("<style>.js-hidden { display: none !important; }</style>")

        # ── Session state ─────────────────────────────────────────────────
        state = gr.State({})

        # ── JS ↔ Python bridge components ────────────────────────────────
        # These must be rendered in the DOM so JS can find and write to them.
        # We hide them visually with CSS (.js-hidden) instead of visible=False,
        # because visible=False can prevent reliable JS interaction.
        idx_ax  = gr.Number(value=0, elem_id="idx-ax",  elem_classes=["js-hidden"])
        idx_cor = gr.Number(value=0, elem_id="idx-cor", elem_classes=["js-hidden"])
        idx_sag = gr.Number(value=0, elem_id="idx-sag", elem_classes=["js-hidden"])
        max_ax  = gr.Number(value=0, elem_id="max-ax",  elem_classes=["js-hidden"])
        max_cor = gr.Number(value=0, elem_id="max-cor", elem_classes=["js-hidden"])
        max_sag = gr.Number(value=0, elem_id="max-sag", elem_classes=["js-hidden"])
        active_view = gr.Number(value=0, elem_id="active-view", elem_classes=["js-hidden"])
        box_coords_json = gr.Textbox(value="", elem_id="box-coords-hidden",
                                     elem_classes=["js-hidden"])

        # ── Header ────────────────────────────────────────────────────────
        gr.Markdown(
            "# 🩺 MedSAM Agent — Three-View\n"
            "Interactive medical image segmentation · "
            "[GitHub](https://github.com/CUHK-AIM-Group/MedSAM-Agent)"
        )

        # ── Top row: load controls + session info ─────────────────────────
        with gr.Row():
            with gr.Column(scale=3):
                file_input = gr.File(
                    label="📂 Upload NIfTI (.nii / .nii.gz)",
                    file_types=[".nii", ".gz"],
                    type="filepath",
                )
                with gr.Row():
                    organ_dd = gr.Dropdown(
                        choices=organs, value=organs[0], label="Target Organ"
                    )
                    backend_dd = gr.Dropdown(
                        choices=backends, value="medsam", label="Backend"
                    )
                    show_mask_chk = gr.Checkbox(value=True, label="Show mask overlay")
                load_btn = gr.Button("🚀 Load Volume", variant="primary")
            with gr.Column(scale=1):
                info_box = gr.Textbox(
                    label="Session Info", lines=4,
                    interactive=False, value="No volume loaded."
                )

        # ── Three-view panel ──────────────────────────────────────────────
        with gr.Row():
            # Axial
            with gr.Column(scale=1):
                img_ax = gr.Image(
                    label="Axial", type="numpy",
                    interactive=False, height=340,
                    elem_id="viewer-ax",
                )
                lbl_ax = gr.Markdown("**Axial** — 0 / ?")

            # Coronal
            with gr.Column(scale=1):
                img_cor = gr.Image(
                    label="Coronal", type="numpy",
                    interactive=False, height=340,
                    elem_id="viewer-cor",
                )
                lbl_cor = gr.Markdown("**Coronal** — 0 / ?")

            # Sagittal
            with gr.Column(scale=1):
                img_sag = gr.Image(
                    label="Sagittal", type="numpy",
                    interactive=False, height=340,
                    elem_id="viewer-sag",
                )
                lbl_sag = gr.Markdown("**Sagittal** — 0 / ?")

        gr.Markdown(
            "_Click a view to activate it (blue border). "
            "Scroll wheel = navigate slices. "
            "Drag on active view = add box prompt._"
        )

        # ── Controls row ──────────────────────────────────────────────────
        with gr.Row():
            # Box prompt panel
            with gr.Column(scale=2):
                gr.Markdown("### 📦 Box Prompt")
                with gr.Accordion("Manual coordinates (fallback)", open=False):
                    with gr.Row():
                        x1_in = gr.Number(label="x1", value=0, precision=0)
                        y1_in = gr.Number(label="y1", value=0, precision=0)
                    with gr.Row():
                        x2_in = gr.Number(label="x2", value=0, precision=0)
                        y2_in = gr.Number(label="y2", value=0, precision=0)
                    add_box_btn = gr.Button("📦 Add Box Prompt")

                gr.Markdown("### 📍 Point Prompt")
                with gr.Row():
                    px_in = gr.Number(label="x", value=64, precision=0)
                    py_in = gr.Number(label="y", value=64, precision=0)
                    lbl_radio = gr.Radio(
                        choices=[("Foreground (1)", 1), ("Background (0)", 0)],
                        value=1, label="Label",
                    )
                add_point_btn = gr.Button("📍 Add Point Prompt")

            # Action panel
            with gr.Column(scale=1):
                gr.Markdown("### ⚡ Actions")
                seg_btn = gr.Button(
                    "🎯 Segment Active Slice", variant="primary", size="lg"
                )
                with gr.Row():
                    clear_btn = gr.Button("🗑️ Clear Slice Prompts")
                propagate_btn = gr.Button(
                    "🌍 Propagate to Full Volume", variant="primary", size="lg"
                )
                gr.Markdown(
                    "_Propagation uses the **active view's axis**. "
                    "Add prompts on 3–5 slices first._"
                )

        # ── Status log ────────────────────────────────────────────────────
        status_log = gr.Textbox(
            label="Status / Log", lines=4,
            interactive=False, value="Ready. Load a NIfTI file to begin.",
        )

        # ── Export & Evaluation ───────────────────────────────────────────
        with gr.Accordion("📤 Export & Evaluation", open=False):
            with gr.Row():
                export_btn = gr.Button("💾 Export Outputs (mask + overlays + JSON)")
                export_status = gr.Textbox(
                    label="Export status", lines=6, interactive=False
                )
                mask_download = gr.File(
                    label="Download mask (.nii.gz)", interactive=False
                )
            gr.Markdown("### Optional: Ground-Truth Evaluation")
            with gr.Row():
                gt_file_inp = gr.File(
                    label="GT mask (.nii / .nii.gz)",
                    file_types=[".nii", ".gz"], type="filepath",
                )
                gt_btn = gr.Button("📊 Load GT & Compute Metrics")
                metrics_out = gr.Textbox(
                    label="Metrics", lines=10, interactive=False
                )

        # ── Quick-start guide ─────────────────────────────────────────────
        with gr.Accordion("ℹ️ Quick-Start Guide", open=False):
            gr.Markdown("""
**Step-by-step workflow:**

1. Upload a `.nii.gz` file.
2. Select organ and backend, then click **Load Volume**.
3. Three views appear: Axial (left), Coronal (centre), Sagittal (right).
4. **Click** any view to activate it (blue border).
5. **Scroll** on any view to navigate that axis independently.
6. **Drag** on the active view to draw a bounding-box — it is added as a prompt automatically.
   - Or expand *Manual coordinates* and type x1/y1/x2/y2, then click **Add Box Prompt**.
7. Click **Segment Active Slice** to run inference.
8. Repeat on 3–5 representative slices.
9. Click **Propagate to Full Volume** (uses the active view's axis).
10. Under *Export & Evaluation*, click **Export Outputs**.
11. Optionally load a GT mask and compute Dice / IoU / HD95.
""")

        # ═══════════════════════════════════════════════════════════════════
        # Wire events
        # ═══════════════════════════════════════════════════════════════════

        # Load volume → set all 3 views + hidden state
        load_btn.click(
            fn=handle_load_volume,
            inputs=[file_input, organ_dd, backend_dd, state],
            outputs=[
                state,
                img_ax, img_cor, img_sag,
                lbl_ax, lbl_cor, lbl_sag,
                idx_ax, idx_cor, idx_sag,
                max_ax, max_cor, max_sag,
                status_log, info_box,
            ],
        )

        # Wheel: each axis updates only its own image + label (no spinner)
        idx_ax.change(
            fn=handle_wheel_ax,
            inputs=[idx_ax, show_mask_chk, state],
            outputs=[img_ax, lbl_ax],
            show_progress="hidden",
        )
        idx_cor.change(
            fn=handle_wheel_cor,
            inputs=[idx_cor, show_mask_chk, state],
            outputs=[img_cor, lbl_cor],
            show_progress="hidden",
        )
        idx_sag.change(
            fn=handle_wheel_sag,
            inputs=[idx_sag, show_mask_chk, state],
            outputs=[img_sag, lbl_sag],
            show_progress="hidden",
        )

        # Active view change (JS → Python state sync)
        active_view.change(
            fn=handle_activate_view,
            inputs=[active_view, state],
            outputs=[state],
            show_progress="hidden",
        )

        # Show mask toggle → re-render all 3 views
        show_mask_chk.change(
            fn=handle_show_mask,
            inputs=[idx_ax, idx_cor, idx_sag, show_mask_chk, state],
            outputs=[img_ax, img_cor, img_sag],
            show_progress="hidden",
        )

        # Canvas drag-draw → auto-add box prompt
        box_coords_json.change(
            fn=handle_box_drawn,
            inputs=[box_coords_json, idx_ax, idx_cor, idx_sag, state],
            outputs=[
                x1_in, y1_in, x2_in, y2_in,
                img_ax, img_cor, img_sag,
                status_log, info_box,
            ],
        )

        # Manual box fallback
        add_box_btn.click(
            fn=handle_add_box,
            inputs=[active_view, idx_ax, idx_cor, idx_sag,
                    x1_in, y1_in, x2_in, y2_in, state],
            outputs=[img_ax, img_cor, img_sag, status_log, info_box],
        )

        # Point prompt
        add_point_btn.click(
            fn=handle_add_point,
            inputs=[active_view, idx_ax, idx_cor, idx_sag,
                    px_in, py_in, lbl_radio, state],
            outputs=[img_ax, img_cor, img_sag, status_log, info_box],
        )

        # Segment active slice
        seg_btn.click(
            fn=handle_segment,
            inputs=[active_view, idx_ax, idx_cor, idx_sag, state],
            outputs=[img_ax, img_cor, img_sag, status_log, info_box],
        )

        # Clear active slice prompts
        clear_btn.click(
            fn=handle_clear,
            inputs=[active_view, idx_ax, idx_cor, idx_sag, state],
            outputs=[img_ax, img_cor, img_sag, status_log, info_box],
        )

        # Propagate
        propagate_btn.click(
            fn=handle_propagate,
            inputs=[active_view, idx_ax, idx_cor, idx_sag, state],
            outputs=[img_ax, img_cor, img_sag, status_log, info_box],
        )

        # Export
        export_btn.click(
            fn=handle_export,
            inputs=[state],
            outputs=[export_status, mask_download],
        )

        # GT evaluation
        gt_btn.click(
            fn=handle_load_gt,
            inputs=[gt_file_inp, idx_ax, idx_cor, idx_sag, show_mask_chk, state],
            outputs=[img_ax, img_cor, img_sag, metrics_out, info_box],
        )

        # Inject three-view JS on page load
        demo.load(fn=None, js=_TRIVIEW_JS)

    return demo


def launch_app(
    port: int = 7860,
    share: bool = False,
    debug: bool = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = build_app()
    app.launch(
        server_port=port,
        share=share,
        debug=debug,
        show_error=True,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    launch_app()
