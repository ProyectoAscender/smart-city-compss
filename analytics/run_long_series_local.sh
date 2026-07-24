#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${1:-${LONG_SERIES_DATA_ROOT:-$PROJECT_ROOT/runs}}"
PORT="${PORT:-5006}"

export LONG_SERIES_DATA_ROOT="$DATA_ROOT"
export BOKEH_PORT="$PORT"
export APP_PATH="$PROJECT_ROOT/analytics/long_series_dashboard.py"

exec "$PROJECT_ROOT/analytics/run_long_series_server.sh"
