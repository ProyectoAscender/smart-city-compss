#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE="${1:-20260712}"

INPUT_DIR="/data/runs/exp/$DATE" exec bash "$PROJECT_ROOT/analytics/run_docker.sh"
