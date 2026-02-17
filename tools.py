
from wavelets import cfc, thresholding, harmonic_wavelets
from hub_detection import detect_hubs_from_graphs
import numpy as np
import argparse
import io
import csv as csv_module
import glob as glob_module
import h5py
import pandas as pd
from datetime import datetime
from utils import corrcoef
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

_ROI_CSV = "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/roi_figs/code_name.csv"
_ROI_FIG_DIR = "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/roi_figs"
_ROI_PALETTE = [
    "#ef4444", "#3b82f6", "#22c55e", "#f59e0b", "#a855f7",
    "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
]


def load_roi_list() -> List[dict]:
    """Load ROI code-name mapping from CSV. Returns list of {code, name} indexed by node position."""
    rows = []
    try:
        with open(_ROI_CSV, newline="") as f:
            for row in csv_module.reader(f):
                if len(row) >= 2:
                    rows.append({"code": row[0].strip(), "name": row[1].strip()})
    except Exception:
        pass
    return rows


def composite_roi_images(roi_ids: List[str]) -> bytes:
    """Composite multiple ROI brain images into one PNG with different colors per region.

    Args:
        roi_ids: List of ROI code strings (e.g. ['2001', '2002'])

    Returns:
        PNG image bytes
    """
    from PIL import Image as _Image
    import io as _io

    base = None
    for i, roi_id in enumerate(roi_ids):
        path = os.path.join(_ROI_FIG_DIR, f"mask{roi_id}_roi.png")
        if not os.path.isfile(path):
            continue
        arr = np.array(_Image.open(path).convert("RGBA"))
        if base is None:
            gray = np.array(_Image.open(path).convert("L"))
            base = np.stack([gray, gray, gray, np.full_like(gray, 255)], axis=-1)
        # Detect pre-rendered colored region: R significantly higher than B
        mask = (arr[:, :, 0].astype(int) - arr[:, :, 2].astype(int) > 80) & (arr[:, :, 3] > 128)
        hex_c = _ROI_PALETTE[i % len(_ROI_PALETTE)]
        base[mask, 0] = int(hex_c[1:3], 16)
        base[mask, 1] = int(hex_c[3:5], 16)
        base[mask, 2] = int(hex_c[5:7], 16)

    if base is None:
        raise FileNotFoundError("No valid ROI images found")

    buf = _io.BytesIO()
    _Image.fromarray(base).save(buf, format="PNG")
    buf.seek(0)
    return buf.read()

# Upload configuration
UPLOAD_DIR = '/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/brain_network_app/brain-network-chart/uploaded_files'
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [UPLOAD] Created upload directory: {UPLOAD_DIR}")


def save_uploaded_file(file_content: bytes, filename: str) -> Tuple[str, dict]:
    """Save an uploaded file to the upload directory.
    
    Args:
        file_content: Binary content of the uploaded file
        filename: Original filename
    
    Returns:
        Tuple of (saved_path, file_info_dict)
    """
    # Validate filename
    if not filename:
        raise ValueError("Filename cannot be empty")

    # Sanitize: allow relative paths (for folder uploads) but reject traversal
    rel = Path(filename).as_posix()
    parts = rel.split('/')
    if '..' in parts or any(p == '' for p in parts[:-1]):
        raise ValueError(f"Invalid filename: {filename}")

    file_path = Path(UPLOAD_DIR) / rel
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file (overwrite existing — caller manages names for folder uploads)
    try:
        with open(file_path, 'wb') as f:
            f.write(file_content)

        file_size = len(file_content)
        saved_rel = rel
        file_info = {
            "original_filename": filename,
            "saved_filename": saved_rel,
            "file_size_bytes": file_size,
            "upload_timestamp": datetime.now().isoformat(),
        }

        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [UPLOAD] File saved: {saved_rel} ({file_size} bytes)")
        return str(file_path), file_info
    except Exception as e:
        raise IOError(f"Failed to save file {filename}: {str(e)}")


def list_uploaded_files() -> list:
    """List uploaded files and folders.

    Returns:
        List of dicts: {filename, size, upload_time, is_dir}
        - Root-level files: filename = "file.csv", is_dir=False
        - Subdirectory entries: filename = "myfolder", is_dir=True
        - Files inside subdirs: filename = "myfolder/file.csv", is_dir=False
    """
    entries = []
    try:
        upload_path = Path(UPLOAD_DIR)
        for item in sorted(upload_path.iterdir()):
            stat = item.stat()
            if item.is_dir():
                entries.append({
                    "filename": item.name,
                    "size": 0,
                    "upload_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "is_dir": True,
                })
                # Also list files inside the subdirectory
                for sub in sorted(item.iterdir()):
                    if sub.is_file():
                        sub_stat = sub.stat()
                        entries.append({
                            "filename": f"{item.name}/{sub.name}",
                            "size": sub_stat.st_size,
                            "upload_time": datetime.fromtimestamp(sub_stat.st_mtime).isoformat(),
                            "is_dir": False,
                        })
            elif item.is_file():
                entries.append({
                    "filename": item.name,
                    "size": stat.st_size,
                    "upload_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "is_dir": False,
                })
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [UPLOAD] Found {len(entries)} entries")
        return entries
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [UPLOAD] Error listing files: {str(e)}")
        return []


def delete_uploaded_file(filename: str) -> dict:
    """Delete an uploaded file.
    
    Args:
        filename: Name of file to delete
    
    Returns:
        Dictionary with deletion status
    """
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {filename}")
    
    if not file_path.startswith(UPLOAD_DIR):
        raise ValueError(f"Invalid file path: {filename}")
    
    try:
        os.remove(file_path)
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [UPLOAD] File deleted: {safe_filename}")
        return {"status": "success", "deleted_file": safe_filename}
    except Exception as e:
        raise IOError(f"Failed to delete file: {str(e)}")


def get_file_path(filename: str, uploaded_only: bool = False) -> str:
    """Get the full path to a file, checking uploads directory first if uploaded_only=True.
    
    Args:
        filename: Filename or relative path
        uploaded_only: If True, only check uploaded_files directory
    
    Returns:
        Full file path
    
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    # If filename is already absolute, return it if it exists
    if os.path.isabs(filename):
        if os.path.exists(filename):
            return filename
        raise FileNotFoundError(f"File not found: {filename}")
    
    # Check uploaded_files directory (support relative paths like "folder/file.csv")
    upload_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(upload_path):
        return upload_path

    # If not uploaded_only, check current directory and relative paths
    if not uploaded_only:
        if os.path.exists(filename):
            return filename

    raise FileNotFoundError(f"File not found: {filename} (checked uploads and current directory)")

class AnalysisConfig():
  
    window: int = 50
    step: int = 3
    padding: bool = True
    ratio: float = 0.8
    wavelets_num: int = 10
    beta: float = 1.0
    gamma: float = 0.005
    max_iter: int = 100
    min_err: float = 1e-6
    node_select: int = 10
    

    k: int = 2
    hub_num: int = 10
    use_group: bool = False
    
    
    x_phenotype: str = 'Global mean of FC'
    y_path: str = ''
    age_col: str = ''
    val_col: str = ''
    

def tool_cfc_wavelet(bolds: np.ndarray, config: AnalysisConfig, precomputed_fcs: bool = False):
        if precomputed_fcs:
            fcs = bolds          # already FC/adj matrices (num_windows, nodes, nodes)
        else:
            fcs = corrcoef(bolds)
        adjs = thresholding(fcs, ratio=config.ratio)
        # graphs = [nx.from_numpy_array(adj) for adj in adjs]
        wavelets_list = []
        num_windows = len(adjs)
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC] Computing wavelets for {num_windows} windows...")
        for i, adj in enumerate(adjs):
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC]   Window {i+1}/{num_windows}: Computing harmonic wavelets...")
            wavelet = harmonic_wavelets(
                adj,
                wavelets_num=config.wavelets_num,
                beta=config.beta,
                gamma=config.gamma,
                max_iter=config.max_iter,
                min_err=config.min_err,
                node_select=config.node_select,
            )
            wavelets_list.append(wavelet)
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC]   Window {i+1}/{num_windows}: Wavelets computed ✓")
        
        cfcs = []
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC] Computing CFC matrices for {num_windows} windows...")
        for i, (wavelet, bold_window) in enumerate(zip(wavelets_list, bolds)):
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC]   Window {i+1}/{num_windows}: Computing CFC matrix...")
            cfc_result = cfc(wavelet, bold_window,config.wavelets_num)
            
            if isinstance(cfc_result, tuple):
                cfc_matrix = cfc_result[0]
            else:
                cfc_matrix = cfc_result

            if isinstance(cfc_matrix, np.ndarray):
                if cfc_matrix.ndim == 3:
                    cfc_2d = np.mean(cfc_matrix, axis=0)
                elif cfc_matrix.ndim == 2:
                    cfc_2d = cfc_matrix
                else:
                    cfc_2d = cfc_matrix.reshape(-1, cfc_matrix.shape[-1])
                
                cfc_clean = np.nan_to_num(cfc_2d, nan=0.0, posinf=0.0, neginf=0.0)
                cfcs.append(cfc_clean.tolist())
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC]   Window {i+1}/{num_windows}: CFC matrix computed ✓")
            else:
                cfcs.append([[0.0]])
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC]   Window {i+1}/{num_windows}: CFC matrix empty, using default")

        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CFC] CFC analysis complete: {len(cfcs)} matrices computed")
        return cfcs

def tool_hub_detection( bolds: np.ndarray, config: AnalysisConfig):
    
        fcs = corrcoef(bolds)
        adjs = thresholding(fcs, ratio=config.ratio)
        # graphs = [nx.from_numpy_array(adj) for adj in adjs]
        
        # Hub Detection
        num_windows = len(adjs)
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUB] Starting hub detection on {num_windows} windows...")
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUB] Configuration: k={config.k}, hub_num={config.hub_num}, use_group={config.use_group}")

        hub_results = detect_hubs_from_graphs(
            adjs,
            k=config.k,
            hub=config.hub_num,
            use_group=config.use_group
        )
        
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [HUB] Hub detection complete")
        return hub_results


def load_bolds_from_csv(path: str, window_size: int = 5, step_size: int = 3, padding: bool = True) -> np.ndarray:
    """Load BOLD data from CSV file with sliding windows.
    
    Supports:
    - Uploaded files in uploaded_files/ directory
    - Local files in current directory
    - Absolute file paths
    
    Expected CSV format: rows are timepoints, columns are nodes.
    Automatically skips unnamed/index columns and non-numeric data.
    
    Args:
        path: Path to the CSV file (can be filename, relative, or absolute path)
        window_size: Size of each sliding window (in timepoints)
        step_size: Number of timepoints to advance between windows
        padding: If True, pads the data to ensure complete windows
    
    Returns:
        np.ndarray of shape (num_windows, num_nodes, window_size)
    """
    # Resolve file path (check uploads first, then local)
    try:
        file_path = get_file_path(path, uploaded_only=False)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Cannot find data file '{path}'. Available uploaded files: {[f['filename'] for f in list_uploaded_files()]}. Error: {str(e)}")
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Reading CSV file: {file_path}")
    df = pd.read_csv(file_path)
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] File loaded: shape {df.shape}")
    
    # Remove unnamed columns (typically index columns from saved CSVs)
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Cleaning columns (removing unnamed columns)...")
    df = df.loc[:, ~df.columns.str.contains('^Unnamed', na=False)]
    
    # Skip any columns that are non-numeric
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Filtering for numeric columns...")
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df = df[numeric_cols]
    if len(df.columns) == 116:
        df = df.iloc[:, :90]
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Numeric columns selected: {len(df.columns)} nodes")

    if df.empty:
        raise ValueError(f"No numeric columns found in {path}")
    
    # Convert to numpy: shape is (num_timepoints, num_nodes)
    data = df.values.astype(np.float32)
    num_timepoints, num_nodes = data.shape
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Data shape: {num_timepoints} timepoints × {num_nodes} nodes")
    
    # Apply padding if needed to ensure we can extract complete windows
    if padding:
        pad_amount = (num_timepoints - window_size) % step_size
        if pad_amount != 0:
            pad_amount = step_size - pad_amount
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Applying padding: {pad_amount} timepoints added")
            data = np.pad(data, ((0, pad_amount), (0, 0)), mode='edge')
            num_timepoints = data.shape[0]
    
    # Extract sliding windows
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Extracting sliding windows (size={window_size}, step={step_size})...")
    windows = []
    for start_idx in range(0, num_timepoints - window_size + 1, step_size):
        window = data[start_idx:start_idx + window_size, :]  # shape: (window_size, num_nodes)
        windows.append(window)
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Windows extracted: {len(windows)} windows")
    
    if not windows:
        raise ValueError(f"No windows could be extracted. Data shape: {data.shape}, "
                        f"window_size: {window_size}, step_size: {step_size}")
    
    # Stack windows: shape (num_windows, window_size, num_nodes)
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Stacking windows...")
    stacked = np.stack(windows, axis=0)
    
    # Transpose to (num_windows, num_nodes, window_size)
    result = np.transpose(stacked, (0, 2, 1))

    return result


def load_bolds_list(path: str) -> List[Tuple[str, np.ndarray]]:
    """Load BOLD data from a file or a folder of CSV files.

    Returns:
        List of (filename, np.ndarray) pairs, each array with shape (1, num_nodes, num_timepoints).
        For a single file: one entry. For a folder: one entry per CSV.
    """
    full = get_file_path(path, uploaded_only=False)
    if os.path.isdir(full):
        csvs = sorted(glob_module.glob(os.path.join(full, '*.csv')))
        if not csvs:
            raise ValueError(f"No CSV files found in folder: {path}")
        return [(os.path.basename(f), load_bolds_full(f)) for f in csvs]
    return [(os.path.basename(path), load_bolds_full(path))]


def list_bold_paths(path: str) -> List[Tuple[str, str]]:
    """Resolve a file or folder path to a list of (basename, fullpath) pairs without loading data."""
    full = get_file_path(path, uploaded_only=False)
    if os.path.isdir(full):
        csvs = sorted(glob_module.glob(os.path.join(full, '*.csv')))
        if not csvs:
            raise ValueError(f"No CSV files found in folder: {path}")
        return [(os.path.basename(f), f) for f in csvs]
    return [(os.path.basename(full), full)]


def load_adjs_from_path(path: str, config) -> List[np.ndarray]:
    """Load adjacency matrices from a file or folder.

    Computes correlation + thresholding per file, returns flat list of adj matrices.
    """
    adjs = []
    for _fname, b in load_bolds_list(path):
        fcs = corrcoef(b)
        adjs.extend(thresholding(fcs, ratio=config.ratio))
    return adjs


def load_bolds_full(path: str) -> np.ndarray:
    """Load full BOLD data without windowing. Returns shape (1, num_nodes, num_timepoints)."""
    try:
        file_path = get_file_path(path, uploaded_only=False)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Cannot find '{path}'. Error: {str(e)}")
    df = pd.read_csv(file_path)
    df = df.loc[:, ~df.columns.str.contains('^Unnamed', na=False)]
    df = df[df.select_dtypes(include=[np.number]).columns]
    if len(df.columns) == 116:
        df = df.iloc[:, :90]
    if df.empty:
        raise ValueError(f"No numeric columns in {path}")
    data = df.values.astype(np.float32)   # (num_timepoints, num_nodes)
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Full BOLD: {data.shape[0]} timepoints × {data.shape[1]} nodes")
    return data.T[np.newaxis]             # (1, num_nodes, num_timepoints)


def load_adjs_from_npy(path: str) -> np.ndarray:
    """Load adjacency matrices from a .npy file.

    Returns shape (num_windows, nodes, nodes).
    Accepts 2D (nodes, nodes) → wrapped to (1, nodes, nodes).
    """
    file_path = get_file_path(path, uploaded_only=False)
    data = np.load(file_path)
    if data.ndim == 2:
        data = data[np.newaxis]   # (1, nodes, nodes)
    elif data.ndim != 3:
        raise ValueError(f"Expected 2D or 3D array in {path}, got shape {data.shape}")
    return data.astype(np.float64)



def load_mat_v73(path: str) -> dict:
    """Load a MATLAB v7.3 .mat file."""
    with h5py.File(path, "r") as f:
        keys = list(f.keys())
        X = np.array(f["X"]).squeeze()
        centiles = np.array(f["centiles"]).T
    
    return {
        "X": X.tolist(),
        "centiles": centiles.tolist(),
    }


def load_curve_data(phenotype: str, 
    PHENOTYPES = {
        "Global mean of FC": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_global_mean_of_FC.mat",
        "Global system segregation": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_global_system_segregation.mat",
        "Visual system segregation (VIS)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_VIS_system_segregation.mat",
        "Somatomotor system segregation (SM)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_SM_system_segregation.mat",
        "Dorsal attention system segregation (DA)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_DA_system_segregation.mat",
        "Ventral attention system segregation (VA)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_VA_system_segregation.mat",
        "Limbic system segregation (LIM)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_LIM_system_segregation.mat",
        "Frontoparietal system segregation (FP)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_FP_system_segregation.mat",
        "Default mode system segregation (DM)": "/ram/USERS/tao/code/gift/BrainChart-FC-Lifespan/Data/Growth_curve_DM_system_segregation.mat",
    }) -> dict:
    """Load growth curve data for a phenotype."""
    
    if phenotype not in PHENOTYPES:
        raise ValueError(f"Phenotype not found. Available: {list(PHENOTYPES.keys())}")
    mat_path = PHENOTYPES[phenotype]
    return load_mat_v73(mat_path)


def _read_table(contents: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(
            io.BytesIO(contents),
            sep=None,
            engine="python",
            on_bad_lines="skip",
            encoding="utf-8",
        )
    except Exception:
        try:
            return pd.read_csv(
                io.BytesIO(contents),
                sep=",",
                on_bad_lines="skip",
                encoding="utf-8",
            )
        except Exception:
            return pd.read_csv(
                io.BytesIO(contents),
                sep="\t",
                on_bad_lines="skip",
                encoding="utf-8",
            )


def overlay_data_from_bytes(contents: bytes, age_col: str, val_col: str) -> dict:
    df = _read_table(contents)

    df.columns = df.columns.str.strip()
    df = df.replace([np.inf, -np.inf], np.nan)

    if age_col not in df.columns or val_col not in df.columns:
        raise ValueError(
            f"Columns not found. Available: {df.columns.tolist()}, "
            f"Requested: age={age_col}, val={val_col}"
        )

    age_raw = df[age_col].to_numpy(dtype=float)
    y_raw = df[val_col].to_numpy(dtype=float)

    valid_mask = ~(np.isnan(age_raw) | np.isnan(y_raw))
    age = age_raw[valid_mask] / 12
    y = y_raw[valid_mask]

    return {
        "age": age.tolist(),
        "values": y.tolist(),
    }


def overlay_data_from_file(path: str, age_col: str, val_col: str) -> dict:
    """Load overlay data from file, supporting uploaded files.
    
    Args:
        path: Path to the overlay data file (can be uploaded file or local path)
        age_col: Column name for age values
        val_col: Column name for metric values
    
    Returns:
        Dictionary with 'age' and 'values' arrays
    """
    try:
        file_path = get_file_path(path, uploaded_only=False)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Cannot find overlay data file '{path}'. Available uploaded files: {[f['filename'] for f in list_uploaded_files()]}. Error: {str(e)}")
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [LOAD] Reading overlay data: {file_path}")
    with open(file_path, "rb") as f:
        contents = f.read()
    return overlay_data_from_bytes(contents, age_col=age_col, val_col=val_col)


def tool_normative_analysis(config: AnalysisConfig) -> dict:
    x_phenotype = config.x_phenotype
    y_path = config.y_path
    age_col = config.age_col
    val_col = config.val_col
    x_data = load_curve_data(x_phenotype)
    y_data = overlay_data_from_file(y_path, age_col=age_col, val_col=val_col)
    return x_data | y_data


def main():
    parser = argparse.ArgumentParser(description="Quick local test for CFC wavelet and hub detection.")
    parser.add_argument("--mode", choices=["cfc", "hub", "normative"], default="hub")
    parser.add_argument("--windows", type=int, default=5)
    parser.add_argument("--nodes", type=int, default=20)
    parser.add_argument("--timepoints", type=int, default=60)
    args = parser.parse_args()

    config = AnalysisConfig()
    bolds = _build_dummy_bolds(args.windows, args.nodes, args.timepoints)

    if args.mode == "hub":
        result = tool_hub_detection(bolds, config)
        if isinstance(result, dict) and result.get("method") == "group":
            hub_nodes = result.get("hub_nodes", [])
            print(f"Hub detection (group): hubs={len(hub_nodes)}")
        else:
            count = len(result.get("results", [])) if isinstance(result, dict) else 0
            print(f"Hub detection (individual): results={count}")
    elif args.mode == "cfc":
        cfcs = tool_cfc_wavelet(bolds, config)
        count = len(cfcs) if isinstance(cfcs, list) else 0
        shape = (len(cfcs[0]), len(cfcs[0][0])) if count and cfcs[0] else None
        print(f"CFC wavelet: windows={count}, first_matrix_shape={shape}")
    else:
        tool_normative_analysis(config)


if __name__ == "__main__":
    main()
