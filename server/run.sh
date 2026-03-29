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

export SSC_LOG_LEVEL="${SSC_LOG_LEVEL:-DEBUG}"
export SSC_BAR_DETECT_FPS="${SSC_BAR_DETECT_FPS:-30}"
export SSC_ACCESS_LOG="${SSC_ACCESS_LOG:-0}"
export SSC_POSE_IMPL="${SSC_POSE_IMPL:-mediapipe}"
export SSC_USE_MODEL_CACHE="${SSC_USE_MODEL_CACHE:-1}"
UVICORN_LOG_LEVEL="$(printf '%s' "$SSC_LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

if [ "$SSC_USE_MODEL_CACHE" = "1" ]; then
  echo "[run.sh] model cache: on"
else
  echo "[run.sh] model cache: off"
fi

UVICORN_ARGS=(
  --reload
  --reload-dir "server"
  --reload-exclude "server/.venv/*"
  --port 8000
  --app-dir "$ROOT_DIR"
  --log-level "$UVICORN_LOG_LEVEL"
)

if [ "$SSC_ACCESS_LOG" != "1" ]; then
  UVICORN_ARGS+=(--no-access-log)
fi

if [ -x "$VENV_BIN/uvicorn" ]; then
  cd "$ROOT_DIR"
  exec "$VENV_BIN/uvicorn" server.main:app "${UVICORN_ARGS[@]}"
fi

cd "$ROOT_DIR"
exec uvicorn server.main:app "${UVICORN_ARGS[@]}"
