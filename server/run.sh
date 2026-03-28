#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT_DIR/server/.venv/bin"
ENV_LOCAL="$ROOT_DIR/server/.env.local"

if [ -f "$ENV_LOCAL" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_LOCAL"
  set +a
fi

export SSC_YOLO_DEVICE="${SSC_YOLO_DEVICE:-mps}"
export SSC_LOG_LEVEL="${SSC_LOG_LEVEL:-DEBUG}"
export SSC_BAR_DETECT_FPS="${SSC_BAR_DETECT_FPS:-30}"

if [ -x "$VENV_BIN/uvicorn" ]; then
  cd "$ROOT_DIR"
  exec "$VENV_BIN/uvicorn" server.main:app \
    --reload \
    --reload-dir "server" \
    --reload-exclude "server/.venv/*" \
    --port 8000 \
    --app-dir "$ROOT_DIR"
fi

cd "$ROOT_DIR"
exec uvicorn server.main:app \
  --reload \
  --reload-dir "server" \
  --reload-exclude "server/.venv/*" \
  --port 8000 \
  --app-dir "$ROOT_DIR"
