#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_DIR="${ROOT_DIR}/cyberneuro_multi-agent-neuroimaging-analysis"
MCP_DIR="${ROOT_DIR}/mcp_server"

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5176}"
VISUALIZER_MODEL="${VISUALIZER_MODEL:-qwen2.5-coder:32b}"

RUN_FRONTEND=1
RUN_PY_QUICK=1
WITH_MCP=0
CHECK_ONLY=0

usage() {
  cat <<'EOF'
Local visualizer smoke test.

Usage:
  bash scripts/local_visualizer_smoke.sh [options]

Options:
  --with-mcp         Start MCP server (8010) and Node backend (8789)
  --no-python-quick  Skip python visualizer quick test
  --no-frontend      Skip frontend startup
  --check-only       Run health checks only, then exit
  -h, --help         Show help

Environment overrides:
  OLLAMA_URL         (default: http://127.0.0.1:11434)
  FRONTEND_HOST      (default: 127.0.0.1)
  FRONTEND_PORT      (default: 5176)
  VISUALIZER_MODEL   (default: qwen2.5-coder:32b)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-mcp)
      WITH_MCP=1
      ;;
    --no-python-quick)
      RUN_PY_QUICK=0
      ;;
    --no-frontend)
      RUN_FRONTEND=0
      ;;
    --check-only)
      CHECK_ONLY=1
      RUN_FRONTEND=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Missing required command: $1" >&2
    exit 1
  fi
}

for cmd in curl python3 npm; do
  require_cmd "$cmd"
done
if [[ "$WITH_MCP" -eq 1 ]]; then
  require_cmd uv
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "ERROR: App directory not found: $APP_DIR" >&2
  exit 1
fi

TAGS_FILE="$(mktemp)"

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  rm -f "$TAGS_FILE" >/dev/null 2>&1 || true

  for pid in "${FRONTEND_PID:-}" "${BACKEND_PID:-}" "${MCP_PID:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done

  exit "$exit_code"
}
trap cleanup EXIT INT TERM

pick_model() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

requested = sys.argv[1]
path = sys.argv[2]

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]

if requested in models:
    print(requested)
    raise SystemExit(0)

preferred = [
    "qwen2.5-coder:32b",
    "qwen2.5-coder:32b-instruct",
    "llama3.1:8b",
    "llama3",
]

for name in preferred:
    if name in models:
        print(name)
        raise SystemExit(0)

for name in models:
    if "coder" in name.lower():
        print(name)
        raise SystemExit(0)

print(models[0] if models else "")
PY
}

wait_for_http() {
  local url="$1"
  local timeout="$2"
  local i

  for ((i=1; i<=timeout; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

echo "[1/5] Checking Ollama at ${OLLAMA_URL} ..."
if ! curl -fsS "${OLLAMA_URL}/api/tags" > "$TAGS_FILE"; then
  echo "ERROR: Ollama is not reachable at ${OLLAMA_URL}" >&2
  echo "Start Ollama, then verify with: curl ${OLLAMA_URL}/api/tags" >&2
  exit 1
fi
echo "OK Ollama is reachable."

SELECTED_MODEL="$(pick_model "$VISUALIZER_MODEL" "$TAGS_FILE")"
if [[ -z "$SELECTED_MODEL" ]]; then
  echo "ERROR: No Ollama models are available. Pull a model first." >&2
  exit 1
fi

if [[ "$SELECTED_MODEL" != "$VISUALIZER_MODEL" ]]; then
  echo "Requested model '${VISUALIZER_MODEL}' not found. Using '${SELECTED_MODEL}' instead."
else
  echo "Using model '${SELECTED_MODEL}'."
fi

if [[ "$RUN_PY_QUICK" -eq 1 ]]; then
  echo "[2/5] Running python visualizer quick test ..."
  if (cd "$APP_DIR" && python3 -c "import bs4, ollama" >/dev/null 2>&1); then
    (cd "$APP_DIR" && python3 visualizer_agent.py --quick ollama "$SELECTED_MODEL")
  else
    echo "WARNING: Python deps missing for quick test."
    echo "Install with: cd $APP_DIR && python3 -m pip install -r requirements.txt"
  fi
else
  echo "[2/5] Skipping python visualizer quick test (--no-python-quick)."
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "Health checks passed. Exiting (--check-only)."
  exit 0
fi

if [[ "$WITH_MCP" -eq 1 ]]; then
  echo "[3/5] Starting MCP server on http://127.0.0.1:8010 ..."
  (
    cd "$MCP_DIR"
    uv sync >/dev/null
    uvicorn mcp_server:http_app --host 127.0.0.1 --port 8010
  ) >/tmp/visualizer_mcp.log 2>&1 &
  MCP_PID=$!

  if ! wait_for_http "http://127.0.0.1:8010/health" 30; then
    echo "ERROR: MCP server failed to start. See /tmp/visualizer_mcp.log" >&2
    exit 1
  fi
  echo "OK MCP server is healthy."

  echo "[4/5] Starting Node backend on http://127.0.0.1:8789 ..."
  (
    cd "$APP_DIR"
    FRONTEND_ORIGIN="http://${FRONTEND_HOST}:${FRONTEND_PORT}" \
    PORT=8789 \
    MCP_SERVER_URL="http://127.0.0.1:8010/mcp" \
    npm run backend
  ) >/tmp/visualizer_backend.log 2>&1 &
  BACKEND_PID=$!

  if ! wait_for_http "http://127.0.0.1:8789/health" 30; then
    echo "ERROR: Backend failed to start. See /tmp/visualizer_backend.log" >&2
    exit 1
  fi
  echo "OK backend is healthy."
else
  echo "[3/5] Skipping MCP/backend startup (--with-mcp to enable)."
fi

if [[ "$RUN_FRONTEND" -eq 1 ]]; then
  if [[ ! -d "$APP_DIR/node_modules" ]]; then
    echo "[4/5] Installing frontend dependencies ..."
    (cd "$APP_DIR" && npm install)
  else
    echo "[4/5] Frontend dependencies already installed."
  fi

  echo "[5/5] Starting frontend on http://${FRONTEND_HOST}:${FRONTEND_PORT} ..."
  (
    cd "$APP_DIR"
    npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) &
  FRONTEND_PID=$!

  if ! wait_for_http "http://${FRONTEND_HOST}:${FRONTEND_PORT}" 60; then
    echo "ERROR: Frontend failed to start on port ${FRONTEND_PORT}." >&2
    exit 1
  fi

  cat <<EOF

Visualizer smoke test is ready.
Open: http://${FRONTEND_HOST}:${FRONTEND_PORT}

Manual verification:
1. Click Demo in chat.
2. Run any query that generates a chart.
3. Click the chart card to enter editing mode.
4. Ask: "change dot color to red".
5. Ask: "swap x and y axes".

Press Ctrl+C to stop services started by this script.
EOF

  wait "$FRONTEND_PID"
fi
