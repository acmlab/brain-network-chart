"""Utilities for turning CIVET outputs into agent-readable JSON."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable


QC_THRESHOLDS = {
    "MASK_ERROR": 10.0,
    "LEFT_INTER": 100.0,
    "RIGHT_INTER": 100.0,
    "SURFACE_INTERSECTIONS": 500.0,
}

FILE_GROUP_PATTERNS = {
    "native_images": (
        "native",
        "nuc",
        "t1",
        "t2",
    ),
    "final_images": (
        "final",
        "stx",
        "stereotaxic",
        "tal",
    ),
    "masks": (
        "mask",
        "brainmask",
        "brain_mask",
        "skull",
    ),
    "classification_files": (
        "classify",
        "classified",
        "classification",
        "cls",
        "tissue",
    ),
    "surfaces": (
        "surface",
        "surf",
        "white",
        "gray",
        "grey",
        "pial",
        "mid",
        "central",
    ),
    "thickness_files": (
        "thick",
        "thickness",
        "tlink",
    ),
    "qc_tables": (
        "qc",
        "quality",
    ),
    "verify_images": (
        "verify",
        "verification",
        "snapshot",
        "montage",
        "png",
        "jpg",
        "jpeg",
    ),
    "logs": (
        "log",
        "stderr",
        "stdout",
    ),
}

IMAGE_SUFFIXES = {".mnc", ".nii", ".gz", ".img", ".hdr", ".mgz"}
TABLE_SUFFIXES = {".csv", ".tsv", ".txt", ".dat"}
SURFACE_SUFFIXES = {".obj", ".surf", ".vtk", ".ply", ".gii", ".mesh"}
VERIFY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff"}
LOG_SUFFIXES = {".log", ".out", ".err"}


def inspect_civet_folder(subject_dir: str) -> dict:
    """Inspect a CIVET subject folder and summarize known output groups."""

    root = Path(subject_dir).expanduser()
    if not root.exists():
        return {
            "status": "error",
            "message": "Subject folder does not exist.",
            "subject_dir": str(root),
        }
    if not root.is_dir():
        return {
            "status": "error",
            "message": "Subject path is not a directory.",
            "subject_dir": str(root),
        }

    groups: dict[str, list[str]] = {group: [] for group in FILE_GROUP_PATTERNS}
    all_files = [path for path in root.rglob("*") if path.is_file()]

    for path in all_files:
        for group in _classify_civet_file(path):
            groups[group].append(_safe_relative(path, root))

    for paths in groups.values():
        paths.sort()

    warnings = [
        f"No {group.replace('_', ' ')} found."
        for group, paths in groups.items()
        if not paths
    ]

    return {
        "status": "warning" if warnings else "ok",
        "subject_dir": str(root),
        "n_files_scanned": len(all_files),
        "groups": {
            group: {"count": len(paths), "files": paths}
            for group, paths in groups.items()
        },
        "warnings": warnings,
    }


def run_civet_qc_check(qc_file: str, subject_id: str | None = None) -> dict:
    """Parse a CIVET QC table and flag common failure thresholds."""

    path = Path(qc_file).expanduser()
    if not path.exists():
        return {
            "status": "error",
            "message": "QC file does not exist.",
            "qc_file": str(path),
        }
    if not path.is_file():
        return {
            "status": "error",
            "message": "QC path is not a file.",
            "qc_file": str(path),
        }

    try:
        rows = _parse_table(path)
    except Exception as exc:  # pragma: no cover - kept defensive for tool use
        return {
            "status": "error",
            "message": f"Could not parse QC file: {exc}",
            "qc_file": str(path),
        }

    if not rows:
        return {
            "status": "error",
            "message": "QC file contains no data rows.",
            "qc_file": str(path),
        }

    selected_rows = _select_subject_rows(rows, subject_id)
    if subject_id is not None and not selected_rows:
        return {
            "status": "error",
            "message": f"Subject '{subject_id}' was not found in the QC file.",
            "qc_file": str(path),
            "subject_id": subject_id,
            "n_rows": len(rows),
        }

    problems = []
    warnings = []
    for row_index, row in selected_rows:
        row_label = _row_subject_id(row) or str(row_index)
        for metric, threshold in QC_THRESHOLDS.items():
            if metric not in row:
                warnings.append(f"Missing QC metric {metric}.")
                continue
            value = _to_float(row.get(metric))
            if value is None:
                warnings.append(f"Metric {metric} is non-numeric for row {row_label}.")
                continue
            if value > threshold:
                problems.append(
                    {
                        "row_index": row_index,
                        "subject_id": _row_subject_id(row),
                        "metric": metric,
                        "value": value,
                        "threshold": threshold,
                        "message": f"{metric}={value:g} exceeds {threshold:g}.",
                    }
                )

    unique_warnings = sorted(set(warnings))
    status = "warning" if problems or unique_warnings else "ok"

    return {
        "status": status,
        "qc_file": str(path),
        "subject_id": subject_id,
        "n_rows": len(rows),
        "n_rows_checked": len(selected_rows),
        "problems": problems,
        "warnings": unique_warnings,
    }


def load_cortical_thickness_map(thickness_file: str) -> dict:
    """Load a CIVET cortical thickness text file and summarize its values."""

    path = Path(thickness_file).expanduser()
    if not path.exists():
        return {
            "status": "error",
            "message": "Thickness file does not exist.",
            "thickness_file": str(path),
        }
    if not path.is_file():
        return {
            "status": "error",
            "message": "Thickness path is not a file.",
            "thickness_file": str(path),
        }

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")

    values = []
    skipped_tokens = []
    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue
        value = _to_float(token)
        if value is None or not math.isfinite(value):
            skipped_tokens.append(token)
            continue
        values.append(value)

    if not values:
        return {
            "status": "error",
            "message": "Thickness file contains no numeric values.",
            "thickness_file": str(path),
            "n_skipped_tokens": len(skipped_tokens),
            "skipped_tokens_preview": skipped_tokens[:10],
        }

    warnings = []
    if skipped_tokens:
        warnings.append(f"Skipped {len(skipped_tokens)} non-numeric token(s).")
    if any(value < 0 for value in values):
        warnings.append("Negative cortical thickness values found.")
    if any(value > 10 for value in values):
        warnings.append("Unusually large cortical thickness values found.")

    return {
        "status": "warning" if warnings else "ok",
        "thickness_file": str(path),
        "n_vertices": len(values),
        "mean_thickness": mean(values),
        "std_thickness": pstdev(values) if len(values) > 1 else 0.0,
        "min_thickness": min(values),
        "max_thickness": max(values),
        "preview_values": values[:10],
        "warnings": warnings,
        "n_skipped_tokens": len(skipped_tokens),
        "skipped_tokens_preview": skipped_tokens[:10],
    }


def visualize_civet_surface(
    surface_path: str,
    overlay_path: str | None = None,
    output_dir: str = "outputs",
) -> dict:
    """Create an interactive Plotly HTML visualization for a CIVET surface."""

    surface = Path(surface_path).expanduser()
    if not surface.exists():
        return {
            "status": "error",
            "message": "Surface file does not exist.",
            "surface_path": str(surface),
        }
    if not surface.is_file():
        return {
            "status": "error",
            "message": "Surface path is not a file.",
            "surface_path": str(surface),
        }

    try:
        vertices, faces, parse_warnings = _parse_obj_surface(surface)
    except ValueError as exc:
        return {
            "status": "error",
            "message": f"Could not parse surface file: {exc}",
            "surface_path": str(surface),
        }
    except OSError as exc:
        return {
            "status": "error",
            "message": f"Could not read surface file: {exc}",
            "surface_path": str(surface),
        }

    warnings = list(parse_warnings)
    overlay_values = None
    overlay = Path(overlay_path).expanduser() if overlay_path else None
    if overlay is not None:
        overlay_result = _load_numeric_values(overlay, label="Overlay")
        if overlay_result["status"] == "error":
            return overlay_result
        overlay_values = overlay_result["values"]
        warnings.extend(overlay_result["warnings"])
        if len(overlay_values) != len(vertices):
            return {
                "status": "error",
                "message": (
                    "Overlay length does not match surface vertex count: "
                    f"{len(overlay_values)} values for {len(vertices)} vertices."
                ),
                "surface_path": str(surface),
                "overlay_path": str(overlay),
                "n_vertices": len(vertices),
                "n_faces": len(faces),
            }

    try:
        figure_path = _write_surface_plot(
            surface=surface,
            vertices=vertices,
            faces=faces,
            overlay_values=overlay_values,
            output_dir=Path(output_dir).expanduser(),
        )
    except ImportError:
        return {
            "status": "error",
            "message": "Plotly is required to generate CIVET surface visualizations.",
            "surface_path": str(surface),
        }
    except Exception as exc:  # pragma: no cover - defensive for filesystem/plotly edges
        return {
            "status": "error",
            "message": f"Could not generate Plotly figure: {exc}",
            "surface_path": str(surface),
        }

    return {
        "status": "warning" if warnings else "ok",
        "figure_path": str(figure_path),
        "surface_path": str(surface),
        "overlay_path": str(overlay) if overlay else None,
        "n_vertices": len(vertices),
        "n_faces": len(faces),
        "warnings": warnings,
    }


def _classify_civet_file(path: Path) -> set[str]:
    groups = set()
    lowered_name = path.name.lower()
    lowered_full_path = str(path).lower()
    suffixes = "".join(path.suffixes).lower()
    suffix = path.suffix.lower()

    if any(term in lowered_full_path for term in FILE_GROUP_PATTERNS["native_images"]):
        if suffix in IMAGE_SUFFIXES or suffixes.endswith(".nii.gz"):
            groups.add("native_images")
    if any(term in lowered_full_path for term in FILE_GROUP_PATTERNS["final_images"]):
        if suffix in IMAGE_SUFFIXES or suffixes.endswith(".nii.gz"):
            groups.add("final_images")
    if any(term in lowered_full_path for term in FILE_GROUP_PATTERNS["masks"]):
        groups.add("masks")
    if any(term in lowered_full_path for term in FILE_GROUP_PATTERNS["classification_files"]):
        groups.add("classification_files")
    if suffix in SURFACE_SUFFIXES or any(
        term in lowered_full_path for term in FILE_GROUP_PATTERNS["surfaces"]
    ):
        groups.add("surfaces")
    if any(term in lowered_full_path for term in FILE_GROUP_PATTERNS["thickness_files"]):
        groups.add("thickness_files")
    if (
        suffix in TABLE_SUFFIXES
        and any(term in lowered_full_path for term in FILE_GROUP_PATTERNS["qc_tables"])
    ):
        groups.add("qc_tables")
    if suffix in VERIFY_SUFFIXES or any(
        term in lowered_name for term in FILE_GROUP_PATTERNS["verify_images"]
    ):
        groups.add("verify_images")
    if suffix in LOG_SUFFIXES or any(
        term in lowered_name for term in FILE_GROUP_PATTERNS["logs"]
    ):
        groups.add("logs")

    return groups


def _parse_obj_surface(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], list[str]]:
    vertices = []
    faces = []
    warnings = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="latin-1").splitlines()

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "v":
            if len(parts) < 4:
                warnings.append(f"Skipped malformed vertex line {line_number}.")
                continue
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                warnings.append(f"Skipped non-numeric vertex line {line_number}.")
        elif parts[0] == "f":
            face_indices = []
            for token in parts[1:]:
                index_text = token.split("/", 1)[0]
                try:
                    index = int(index_text)
                except ValueError:
                    warnings.append(f"Skipped malformed face line {line_number}.")
                    face_indices = []
                    break
                if index == 0:
                    warnings.append(f"Skipped zero-indexed face line {line_number}.")
                    face_indices = []
                    break
                face_indices.append(index - 1 if index > 0 else len(vertices) + index)
            if len(face_indices) < 3:
                continue
            for triangle in _triangulate_face(face_indices):
                if any(index < 0 or index >= len(vertices) for index in triangle):
                    warnings.append(f"Skipped out-of-range face line {line_number}.")
                    continue
                faces.append(triangle)

    if not vertices:
        raise ValueError("no Wavefront OBJ vertex lines were found.")
    if not faces:
        raise ValueError("no Wavefront OBJ face lines were found.")

    return vertices, faces, sorted(set(warnings))


def _triangulate_face(indices: list[int]) -> list[tuple[int, int, int]]:
    return [(indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1)]


def _load_numeric_values(path: Path, label: str) -> dict:
    if not path.exists():
        return {
            "status": "error",
            "message": f"{label} file does not exist.",
            "overlay_path": str(path),
        }
    if not path.is_file():
        return {
            "status": "error",
            "message": f"{label} path is not a file.",
            "overlay_path": str(path),
        }

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")

    values = []
    skipped_tokens = []
    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue
        value = _to_float(token)
        if value is None or not math.isfinite(value):
            skipped_tokens.append(token)
            continue
        values.append(value)

    if not values:
        return {
            "status": "error",
            "message": f"{label} file contains no numeric values.",
            "overlay_path": str(path),
        }

    warnings = []
    if skipped_tokens:
        warnings.append(f"Skipped {len(skipped_tokens)} non-numeric overlay token(s).")

    return {"status": "ok", "values": values, "warnings": warnings}


def _write_surface_plot(
    surface: Path,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    overlay_values: list[float] | None,
    output_dir: Path,
) -> Path:
    import plotly.graph_objects as go

    output_dir.mkdir(parents=True, exist_ok=True)
    figure_path = output_dir / f"{surface.stem}_surface.html"
    x, y, z = zip(*vertices, strict=True)
    i, j, k = zip(*faces, strict=True)

    mesh_kwargs = {
        "x": list(x),
        "y": list(y),
        "z": list(z),
        "i": list(i),
        "j": list(j),
        "k": list(k),
        "opacity": 1.0,
        "flatshading": False,
        "name": surface.name,
    }
    if overlay_values is None:
        mesh_kwargs.update(
            {
                "color": "lightsteelblue",
                "lighting": {"ambient": 0.45, "diffuse": 0.8, "specular": 0.15},
            }
        )
    else:
        mesh_kwargs.update(
            {
                "intensity": overlay_values,
                "colorscale": "Viridis",
                "showscale": True,
                "colorbar": {"title": "Overlay"},
            }
        )

    fig = go.Figure(data=[go.Mesh3d(**mesh_kwargs)])
    fig.update_layout(
        title=f"CIVET surface: {surface.name}",
        scene={
            "aspectmode": "data",
            "xaxis": {"title": "X"},
            "yaxis": {"title": "Y"},
            "zaxis": {"title": "Z"},
        },
        margin={"l": 0, "r": 0, "t": 48, "b": 0},
    )
    fig.write_html(str(figure_path), include_plotlyjs="cdn", full_html=True)
    return figure_path


def _parse_table(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    delimiter = _detect_delimiter(lines[0])
    if delimiter is None:
        header = re.split(r"\s+", lines[0])
        rows = []
        for line in lines[1:]:
            cells = re.split(r"\s+", line)
            rows.append(_zip_row(header, cells))
        return rows

    reader = csv.DictReader(lines, delimiter=delimiter)
    return [
        {str(key).strip(): (value or "").strip() for key, value in row.items() if key}
        for row in reader
    ]


def _detect_delimiter(header_line: str) -> str | None:
    if "\t" in header_line:
        return "\t"
    if "," in header_line:
        return ","
    if ";" in header_line:
        return ";"
    return None


def _zip_row(header: Iterable[str], cells: Iterable[str]) -> dict[str, str]:
    return {
        str(key).strip(): str(value).strip()
        for key, value in zip(header, cells, strict=False)
    }


def _select_subject_rows(
    rows: list[dict[str, str]], subject_id: str | None
) -> list[tuple[int, dict[str, str]]]:
    indexed_rows = list(enumerate(rows, start=1))
    if subject_id is None:
        return indexed_rows
    return [
        (index, row)
        for index, row in indexed_rows
        if _row_subject_id(row) == subject_id
    ]


def _row_subject_id(row: dict[str, str]) -> str | None:
    for key in ("subject_id", "SUBJECT_ID", "subject", "SUBJECT", "id", "ID"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
