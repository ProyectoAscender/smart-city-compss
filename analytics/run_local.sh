#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_DIR="${1:-$PROJECT_ROOT/runs/exp/20260712}"
PORT="${PORT:-8090}"
HOST="${HOST:-0.0.0.0}"
VIDEO_START_TIME="${VIDEO_START_TIME:-}"

ARGS=(--input-dir "$INPUT_DIR" --host "$HOST" --port "$PORT")
if [ -n "$VIDEO_START_TIME" ]; then
  ARGS+=(--video-start-time "$VIDEO_START_TIME")
fi

exec python3 "$PROJECT_ROOT/analytics/app.py" "${ARGS[@]}"
