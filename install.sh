#!/bin/bash
# install.sh — set up brain-network-chart environment
# Installs: conda env (Python deps + dcm2bids + dcm2niix + pydicom + httpx),
#           Node.js bids-validator (via npm), frontend build
#
# Requirements: conda, node.js 18+
# Usage: bash install.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Conda environment ─────────────────────────────────────────────────────────

CONDA_BASE="$(conda info --base 2>/dev/null || echo "")"
if [[ -z "${CONDA_BASE}" ]]; then
    echo "[ERROR] conda not found. Install Miniconda first:"
    echo "  https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi
source "${CONDA_BASE}/etc/profile.d/conda.sh"

ENV_NAME="brainchart"

if conda env list | grep -q "^${ENV_NAME} "; then
    echo "[INFO] conda env '${ENV_NAME}' already exists — skipping creation"
else
    echo "[INFO] Creating conda env '${ENV_NAME}' (Python 3.11) ..."
    conda create -y -n "${ENV_NAME}" python=3.11
fi

echo "[INFO] Installing Python packages ..."
conda run -n "${ENV_NAME}" pip install --quiet \
    "duckduckgo-search>=8.1.1" \
    "h5py>=3.10.0" \
    "mcp>=1.0.0" \
    "numpy>=1.26.0" \
    "pandas>=2.0.0" \
    "pydantic>=2.0.0" \
    "pydantic-ai>=1.51.0" \
    "scipy>=1.11.0" \
    statsmodels ollama \
    fastapi uvicorn \
    "python-multipart>=0.0.9" \
    "requests>=2.31.0" \
    "starlette>=0.37.0" \
    "pillow>=10.0" \
    httpx \
    pydicom \
    dcm2bids \
    dcm2niix

echo "[INFO] Verifying tools ..."
conda run -n "${ENV_NAME}" python - <<'PY'
import shutil, sys
for tool in ("dcm2bids", "dcm2niix"):
    p = shutil.which(tool)
    if p:
        print(f"  ✓ {tool}: {p}")
    else:
        print(f"  ✗ {tool}: NOT FOUND after install", file=sys.stderr)
        sys.exit(1)
for pkg in ("httpx", "pydicom"):
    try:
        __import__(pkg)
        print(f"  ✓ {pkg}")
    except ImportError:
        print(f"  ✗ {pkg}: NOT FOUND", file=sys.stderr)
        sys.exit(1)
PY

# ── bids-validator (Node.js) ──────────────────────────────────────────────────

echo ""
if command -v npm &>/dev/null; then
    echo "[INFO] Installing bids-validator globally via npm ..."
    npm install -g bids-validator --silent
    echo "  ✓ bids-validator: $(which bids-validator 2>/dev/null || echo 'installed via npm')"
elif command -v npx &>/dev/null; then
    echo "[INFO] npx found — bids-validator will be downloaded on first use (npx --yes bids-validator)"
else
    echo "[WARN] Node.js / npm not found — bids-validator will be skipped during conversion"
    echo "       Install Node.js 18+ from https://nodejs.org to enable validation"
fi

# ── Frontend build ────────────────────────────────────────────────────────────

echo ""
if command -v node &>/dev/null; then
    echo "[INFO] Building frontend ..."
    cd "${SCRIPT_DIR}/frontend"
    npm install --silent
    npm run build
    echo "  ✓ Frontend built → frontend/dist/"
else
    echo "[WARN] node.js not found — frontend not built"
    echo "       Install Node.js 18+ and re-run this script, or use 'npm run dev' for development"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "========================================"
echo " Installation complete!"
echo " Open: http://localhost:8005"
echo "========================================"
