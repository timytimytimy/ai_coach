#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT_DIR/server/.venv/bin"

export SSC_YOLO_DEVICE="${SSC_YOLO_DEVICE:-mps}"
export SSC_LOG_LEVEL="${SSC_LOG_LEVEL:-DEBUG}"
export SSC_BAR_DETECT_FPS="${SSC_BAR_DETECT_FPS:-30}"

if [ -x "$VENV_BIN/uvicorn" ]; then
  exec "$VENV_BIN/uvicorn" server.main:app --reload --port 8000 --app-dir "$ROOT_DIR"
fi

exec uvicorn server.main:app --reload --port 8000 --app-dir "$ROOT_DIR"
