#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT_DIR/server/.venv/bin"
ENV_LOCAL="$ROOT_DIR/server/.env.local"

CLI_SSC_LOG_LEVEL="${SSC_LOG_LEVEL-}"
CLI_SSC_BAR_DETECT_FPS="${SSC_BAR_DETECT_FPS-}"
CLI_SSC_ACCESS_LOG="${SSC_ACCESS_LOG-}"
CLI_SSC_POSE_IMPL="${SSC_POSE_IMPL-}"
CLI_SSC_USE_MODEL_CACHE="${SSC_USE_MODEL_CACHE-}"
CLI_SSC_COACH_SOUL="${SSC_COACH_SOUL-}"
CLI_SSC_LLM_MODEL="${SSC_LLM_MODEL-}"
CLI_OPENAI_MODEL="${OPENAI_MODEL-}"

if [ -f "$ENV_LOCAL" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_LOCAL"
  set +a
fi

if [ -n "${CLI_SSC_LOG_LEVEL}" ]; then export SSC_LOG_LEVEL="$CLI_SSC_LOG_LEVEL"; fi
if [ -n "${CLI_SSC_BAR_DETECT_FPS}" ]; then export SSC_BAR_DETECT_FPS="$CLI_SSC_BAR_DETECT_FPS"; fi
if [ -n "${CLI_SSC_ACCESS_LOG}" ]; then export SSC_ACCESS_LOG="$CLI_SSC_ACCESS_LOG"; fi
if [ -n "${CLI_SSC_POSE_IMPL}" ]; then export SSC_POSE_IMPL="$CLI_SSC_POSE_IMPL"; fi
if [ -n "${CLI_SSC_USE_MODEL_CACHE}" ]; then export SSC_USE_MODEL_CACHE="$CLI_SSC_USE_MODEL_CACHE"; fi
if [ -n "${CLI_SSC_COACH_SOUL}" ]; then export SSC_COACH_SOUL="$CLI_SSC_COACH_SOUL"; fi
if [ -n "${CLI_SSC_LLM_MODEL}" ]; then export SSC_LLM_MODEL="$CLI_SSC_LLM_MODEL"; fi
if [ -n "${CLI_OPENAI_MODEL}" ]; then export OPENAI_MODEL="$CLI_OPENAI_MODEL"; fi

export SSC_LOG_LEVEL="${SSC_LOG_LEVEL:-DEBUG}"
export SSC_BAR_DETECT_FPS="${SSC_BAR_DETECT_FPS:-30}"
export SSC_ACCESS_LOG="${SSC_ACCESS_LOG:-0}"
export SSC_POSE_IMPL="${SSC_POSE_IMPL:-mediapipe}"
export SSC_USE_MODEL_CACHE="${SSC_USE_MODEL_CACHE:-1}"
export SSC_COACH_SOUL="${SSC_COACH_SOUL:-balanced}"
export SSC_LLM_MODEL="${SSC_LLM_MODEL:-gemini-3-pro-preview-new}"
UVICORN_LOG_LEVEL="$(printf '%s' "$SSC_LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

if [ "$SSC_USE_MODEL_CACHE" = "1" ]; then
  echo "[run.sh] model cache: on"
else
  echo "[run.sh] model cache: off"
fi
echo "[run.sh] coach soul: $SSC_COACH_SOUL"
echo "[run.sh] llm model: $SSC_LLM_MODEL"
echo "[run.sh] pose impl: $SSC_POSE_IMPL"

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
