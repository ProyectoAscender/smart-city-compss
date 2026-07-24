#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-smart-city-analytics:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-smart-city-analytics}"
PORT="${PORT:-8090}"
INPUT_DIR="${INPUT_DIR:-/data/runs/exp/20260712}"
VIDEO_START_TIME="${VIDEO_START_TIME:-}"

docker build -f "$PROJECT_ROOT/analytics/Dockerfile" -t "$IMAGE_NAME" "$PROJECT_ROOT"

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

docker run --rm -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:8090" \
  -e PORT=8090 \
  -e HOST=0.0.0.0 \
  -e INPUT_DIR="$INPUT_DIR" \
  -e VIDEO_START_TIME="$VIDEO_START_TIME" \
  -v "$PROJECT_ROOT/runs:/data/runs:ro" \
  "$IMAGE_NAME"

echo "Analytics available at http://localhost:$PORT"
