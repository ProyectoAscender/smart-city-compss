#!/usr/bin/env bash
set -euo pipefail

PORT="${BOKEH_PORT:-5006}"
APP_PATH="${APP_PATH:-/app/analytics/long_series_dashboard.py}"
ALLOW_ORIGINS="${BOKEH_ALLOW_ORIGINS:-localhost:${PORT},127.0.0.1:${PORT}}"

declare -a ORIGIN_ARGS=()
IFS=',' read -r -a ORIGIN_ITEMS <<< "$ALLOW_ORIGINS"
for origin in "${ORIGIN_ITEMS[@]}"; do
  origin="$(echo "$origin" | xargs)"
  if [[ -n "$origin" ]]; then
    ORIGIN_ARGS+=(--allow-websocket-origin="$origin")
  fi
done

exec bokeh serve "$APP_PATH" \
  --address 0.0.0.0 \
  --port "$PORT" \
  --num-procs 1 \
  "${ORIGIN_ARGS[@]}"
