#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${1:-}"
PORT="${PORT:-5006}"
IMAGE_NAME="${IMAGE_NAME:-smart-city-long-series:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-smart-city-long-series}"

if [[ -z "$DATA_ROOT" ]]; then
  echo "Usage: bash analytics/run_long_series_docker.sh <data_root>"
  exit 1
fi

docker build -f "$PROJECT_ROOT/analytics/Dockerfile_long_series" -t "$IMAGE_NAME" "$PROJECT_ROOT"

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:5006" \
  -e LONG_SERIES_DATA_ROOT=/data/traffic-data \
  -e LONG_SERIES_APP_TITLE="Smart City Long-Series Speeds" \
  -e LONG_SERIES_MAX_POINTS=4000 \
  -e BOKEH_PORT=5006 \
  -e BOKEH_ALLOW_ORIGINS="localhost:${PORT},127.0.0.1:${PORT}" \
  -v "$DATA_ROOT:/data/traffic-data:ro" \
  "$IMAGE_NAME"

echo "Long-series dashboard available at http://localhost:$PORT/long_series_dashboard"
