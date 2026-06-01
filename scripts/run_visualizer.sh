#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Smart City — Traffic Visualizer
#  Builds the Docker image and starts the container on port 8080.
#
#  ACCESS FROM YOUR LOCAL MACHINE (SSH tunnel on port 22):
#
#    ssh -N -L 8080:localhost:8080 <user>@<remote-host>
#
#    Then open in your browser:  http://localhost:8080
#
#  If your SSH daemon listens on a non-standard port, specify it:
#
#    ssh -N -L 8080:localhost:8080 -p <ssh-port> <user>@<remote-host>
#
#  The -N flag keeps the tunnel open without spawning a shell.
#  Run in background with -f:
#
#    ssh -f -N -L 8080:localhost:8080 <user>@<remote-host>
#
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

IMAGE="smart-city-visualizer:latest"
CONTAINER="visualizer"

echo "[build] Building $IMAGE (context: $PROJECT_ROOT) …"
docker build \
  -f "$PROJECT_ROOT/visualizer/Dockerfile" \
  -t "$IMAGE" \
  "$PROJECT_ROOT"

# Remove any existing container with the same name
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "[cleanup] Removing existing container '$CONTAINER' …"
  docker rm -f "$CONTAINER"
fi

echo "[run] Starting $CONTAINER on :8080 …"
docker run -d \
  --name "$CONTAINER" \
  -p 8080:8080 \
  -v "$PROJECT_ROOT/data_cache:/app/data_cache:ro" \
  -v "$PROJECT_ROOT/runs:/app/runs:ro" \
  -v "$PROJECT_ROOT/.env:/app/.env:ro" \
  "$IMAGE"

echo ""
echo "  ✓ Visualizer running"
echo "    → local:  http://localhost:8080"
echo "    → remote: ssh -N -L 8080:localhost:8080 <user>@$(hostname -I | awk '{print $1}' 2>/dev/null || echo '<remote-host>')"
echo ""
echo "  Stop:  docker stop $CONTAINER"
echo "  Logs:  docker logs -f $CONTAINER"
