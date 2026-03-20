# MedSAM Agent

**Interactive medical image segmentation agent** — inference-first, production-ready.

Inspired by [MedSAM-Agent (CUHK-AIM-Group)](https://github.com/CUHK-AIM-Group/MedSAM-Agent),
reimplemented as a deployable, extensible system for real clinical data workflows.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        User (UI / CLI)                           │
└───────────────────┬──────────────────────────────────────────────┘
                    │  prompts (box / point) + actions
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Gradio Web UI (app/ui/)                        │
│  • Volume browser (slice slider, 3 axes)                          │
│  • Box / point prompt entry                                       │
│  • Overlay viewer                                                 │
│  • Export / GT evaluation panel                                   │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│              SegmentationOrchestrator (app/agent/)                │
│  • Session management (case, organ, axis, GT mode)                │
│  • PromptManager: stores box/point prompts per slice              │
│  • Triggers model inference for prompted slices                   │
│  • Calls Propagator for full-volume mask                          │
│  • Writes outputs, computes metrics                               │
└───────┬────────────────────────────────┬─────────────────────────┘
        │                                │
        ▼                                ▼
┌────────────────────┐         ┌─────────────────────────┐
│   Model Adapters   │         │      Propagator          │
│   (app/models/)    │         │   (app/core/)            │
│                    │         │                          │
│ • MedSAMAdapter    │         │ • sam_guided (default)   │
│ • SAMAdapter       │         │ • SDF interpolation      │
│ • MockAdapter      │         │ • nearest-copy           │
└────────────────────┘         └─────────────────────────┘
        │
        ▼
┌────────────────────┐
│   I/O + Eval       │
│   (app/io/, eval/) │
│ • NIfTI read/write │
│ • PNG overlays     │
│ • Dice/IoU/HD95    │
└────────────────────┘
```

---

## Features

| Feature | Status |
|---|---|
| NIfTI volume loading | ✅ Fully implemented |
| Intensity normalization (MR/CT) | ✅ Fully implemented |
| MedSAM ViT-B inference (box prompt) | ✅ Fully implemented |
| SAM inference (box + point) | ✅ Fully implemented |
| Mock backend (no GPU) | ✅ Fully implemented |
| Gradio web UI with slice viewer | ✅ Fully implemented |
| Box prompt via UI | ✅ Fully implemented |
| Point prompt via UI | ✅ Fully implemented |
| 3D propagation (3 strategies) | ✅ Fully implemented |
| Inference-only mode (no GT) | ✅ First-class support |
| GT evaluation (Dice/IoU/HD95) | ✅ Fully implemented |
| NIfTI mask export | ✅ Fully implemented |
| PNG overlay export | ✅ Fully implemented |
| Prompts JSON export | ✅ Fully implemented |
| CLI: single case | ✅ Fully implemented |
| CLI: batch processing | ✅ Fully implemented |
| CLI: evaluate | ✅ Fully implemented |
| Multi-round refinement | ✅ Basic (re-run with new prompt) |
| Scribble prompts | ⚠️ Planned (stub in place) |
| RL-based agent planning | ❌ Out of scope for v1 |
| Training pipeline | ❌ Out of scope for v1 |

---

## Installation

### 1. Clone and enter the project

```bash
cd /ram/USERS/zhuoyu73/Andy
# (project is already at medsam/)
```

### 2. Environment (already satisfied in this environment)

```bash
pip install nibabel gradio pyyaml python-dotenv loguru scipy scikit-image pillow tqdm
# torch is assumed installed (2.5.1+cu121 or similar)
```

### 3. Configure

```bash
cp medsam/.env.example medsam/.env
# Edit medsam/.env:
#   MEDSAM_CHECKPOINT=/ram/USERS/zhuoyu73/Andy/MedSAM_COPY/work_dir/MedSAM/medsam_vit_b.pth
#   SEGMENT_ANYTHING_PATH=/ram/USERS/zhuoyu73/Andy/MedSAM_COPY
#   DEVICE=cuda
#   KIDNEY_DATA_DIR=/proj/data/UKB_KidneyMRI_ShMOLLI
#   HEART_DATA_DIR=/proj/data/UKB_HeartMRI_ShMOLLI
```

---

## Directory Structure

```
medsam/
├── README.md
├── requirements.txt
├── .env.example
├── .env                        # (create from .env.example)
│
├── config/
│   ├── default.yaml            # All system defaults
│   └── organs.yaml             # Organ metadata (colors, windows, labels)
│
├── app/
│   ├── config_loader.py        # YAML + env var merging
│   ├── __init__.py
│   │
│   ├── io/                     # Data I/O
│   │   ├── nifti_reader.py     # NiftiReader, load_nifti, normalize_intensity
│   │   └── image_writer.py     # save_mask_nifti, save_overlay_png, etc.
│   │
│   ├── models/                 # Model adapters
│   │   ├── base_adapter.py     # Abstract BaseSegAdapter, Prompt, SegResult
│   │   ├── medsam_adapter.py   # MedSAM ViT-B (box-prompted)
│   │   ├── sam_adapter.py      # Vanilla SAM (box + point)
│   │   └── mock_adapter.py     # Synthetic ellipse (no GPU needed)
│   │
│   ├── agent/                  # Orchestration
│   │   ├── orchestrator.py     # SegmentationOrchestrator (main controller)
│   │   └── prompt_manager.py   # PromptManager (prompt CRUD + serialization)
│   │
│   ├── core/                   # Session + propagation
│   │   ├── session.py          # Session state & audit log
│   │   └── propagation.py      # Propagator (3 strategies)
│   │
│   ├── eval/                   # Metrics
│   │   └── metrics.py          # Dice, IoU, Precision, Recall, HD95, VolDiff
│   │
│   └── ui/
│       └── gradio_app.py       # Gradio Blocks web app
│
├── scripts/
│   ├── run_ui.py               # Launch web UI
│   ├── run_single_case.py      # CLI: single case inference
│   ├── run_batch.py            # CLI: batch inference
│   ├── evaluate.py             # CLI: evaluation against GT
│   └── create_demo_volume.py   # Create synthetic demo volume
│
├── tests/
│   ├── test_io.py
│   ├── test_metrics.py
│   └── test_propagation.py
│
└── output/                     # All outputs go here (per-case subdirs)
    └── <case_id>/
        ├── pred_mask.nii.gz
        ├── overlay_grid.png
        ├── prompts.json
        ├── session_log.json
        └── metrics.json        # only if GT was provided
```

---

## Quick Start

### 1. Create a synthetic demo volume

```bash
cd /ram/USERS/zhuoyu73/Andy/medsam
python scripts/create_demo_volume.py --output output/demo_volume.nii.gz --with-mask
```

### 2. Run single-case inference (mock backend, no GPU needed)

```bash
python scripts/run_single_case.py \
  --input output/demo_volume.nii.gz \
  --backend mock \
  --organ "right kidney" \
  --slice 30 \
  --box 40 40 90 90 \
  --propagate
```

### 3. Run with MedSAM (requires GPU + checkpoint)

```bash
python scripts/run_single_case.py \
  --input /proj/data/UKB_KidneyMRI_ShMOLLI/sub-001.nii.gz \
  --organ "right kidney" \
  --slice 45 \
  --box 80 60 200 180 \
  --propagate
```

### 4. Launch the Web UI

```bash
python scripts/run_ui.py --port 7860
# Open http://localhost:7860
```

### 5. Batch processing

```bash
python scripts/run_batch.py \
  --input-dir /proj/data/UKB_KidneyMRI_ShMOLLI \
  --organ "right kidney" \
  --slice 45 \
  --box 80 60 200 180 \
  --propagate
```

### 6. Evaluate against GT

```bash
# Single case
python scripts/evaluate.py \
  --pred output/sub-001/pred_mask.nii.gz \
  --gt /proj/data/gt_masks/sub-001_mask.nii.gz

# Batch
python scripts/evaluate.py \
  --pred-dir output/ \
  --gt-dir /proj/data/gt_masks/
```

---

## Configuring Your Data

Edit `medsam/.env` (copy from `.env.example`):

```bash
KIDNEY_DATA_DIR=/proj/data/UKB_KidneyMRI_ShMOLLI
HEART_DATA_DIR=/proj/data/UKB_HeartMRI_ShMOLLI
MEDSAM_CHECKPOINT=/ram/USERS/zhuoyu73/Andy/MedSAM_COPY/work_dir/MedSAM/medsam_vit_b.pth
SEGMENT_ANYTHING_PATH=/ram/USERS/zhuoyu73/Andy/MedSAM_COPY
DEVICE=cuda
OUTPUT_DIR=/ram/USERS/zhuoyu73/Andy/medsam/output
```

---

## UI Workflow

```
1. Upload NIfTI → select organ + axis → Load Volume
2. Navigate slice slider to representative slice
3. Enter box coordinates (x1, y1, x2, y2) → Add Box Prompt
4. Click "Segment This Slice" → see overlay
5. Repeat on 3–5 key slices
6. Click "Propagate to Full Volume"
7. Export → download pred_mask.nii.gz
8. (Optional) Upload GT mask → compute metrics
```

---

## 3D Propagation Strategy

**Current default: `sam_guided`**

For each unprompted slice, the propagator:
1. Finds the nearest already-segmented slice.
2. Derives a bounding box from its mask (with a small expansion).
3. Runs the model on the current slice using that derived box as prompt.

This gives better anatomical accuracy than pure interpolation but requires
a loaded model. Two simpler fallbacks are available:

- **`interpolate`**: Signed-distance-field linear interpolation between
  seed masks + forward/backward copy at boundaries.
- **`nearest`**: Copy nearest seed mask to every unprompted slice.

Configure in `config/default.yaml` → `propagation.strategy`.

**Current limitation**: no temporal video-SAM propagation; each slice is
independent. This works well for anatomy with gradual shape change across
slices (kidney, heart), but may struggle with rapid topology changes.

---

## Inference-Only Mode

When no GT mask is provided (the normal situation for UKB kidney data):

- System runs normally and produces `pred_mask.nii.gz` + overlays.
- Metrics are skipped with an informational log message.
- `session_log.json` records `has_gt: false`.
- The UI shows "⚠️ No GT (inference-only)" in the info panel.

There is no special mode to switch to — this is the default.

---

## Tested On

- Python 3.12.7
- PyTorch 2.5.1+cu121
- CUDA 12.1
- nibabel 5.3.3
- gradio 6.8.0
- MedSAM checkpoint: `medsam_vit_b.pth`

---

## Known Limitations

1. **Box prompts only for MedSAM**: MedSAM's decoder is trained with box
   prompts. Point-only prompts require SAM adapter.
2. **UI coordinate input**: The current UI requires manual entry of pixel
   coordinates. Future: canvas-based click-drag box drawing.
3. **No temporal coherence**: Propagation does not use video-SAM or
   optical-flow-based tracking — each slice is segmented independently.
4. **Single-session UI**: The Gradio UI supports one active session at a
   time. Multi-user deployment needs a session-ID system.
5. **HD95 speed**: HD95 on large 3D volumes can take 10–30s. Use `--no-hd95`
   for batch evaluation if speed matters.
6. **Scribble prompts**: Stubbed in PromptManager but not wired to model.
7. **No training pipeline**: This v1 is purely inference-focused.

---

## vs Reference Repo (MedSAM-Agent)

| Aspect | MedSAM-Agent (reference) | This system |
|---|---|---|
| Goal | Research + RL agent | Production inference agent |
| Prompt type | Box (primary) | Box + point (SAM), box (MedSAM) |
| 3D workflow | Paper-level | Pragmatic propagation |
| UI | Minimal | Gradio web app |
| GT required | For training/eval | Optional (inference-only is default) |
| Training | RL policy | Not included in v1 |
| Data focus | General | Kidney MRI + Heart MRI |

---

## Next Steps (Priority Order)

1. **Canvas-based box drawing in UI**: Replace numeric input with click-drag
   on the image. Use Gradio custom components or a lightweight JS canvas.
2. **Video-SAM propagation**: Integrate SAM2 video predictor for temporally
   coherent propagation (much better for 3D anatomy).
3. **Multi-structure segmentation**: Allow multiple organs per session with
   separate label values per structure.
