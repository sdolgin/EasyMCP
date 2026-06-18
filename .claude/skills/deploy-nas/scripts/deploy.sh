#!/usr/bin/env bash
# Deploy EasyMCP to Synology NAS via GHCR pull.
# Usage: deploy.sh <nas-user> <nas-ip> [ssh-port]
#
# This script SSHes into the NAS, pulls the latest image, and recreates
# the container. It does NOT copy source files — use scp separately if
# Dockerfile or compose changed.

set -euo pipefail

NAS_USER="${1:?Usage: deploy.sh <nas-user> <nas-ip> [ssh-port]}"
NAS_IP="${2:?Usage: deploy.sh <nas-user> <nas-ip> [ssh-port]}"
SSH_PORT="${3:-22}"
REMOTE_DIR="/volume1/tools/easynews-mcp"

echo "==> Pulling latest image and recreating container on ${NAS_IP}..."
ssh -p "${SSH_PORT}" "${NAS_USER}@${NAS_IP}" "
  cd ${REMOTE_DIR} &&
  sudo docker-compose pull &&
  sudo docker-compose up -d --force-recreate &&
  echo '==> Waiting for healthcheck...' &&
  sleep 10 &&
  sudo docker-compose ps
"

echo "==> Verifying health endpoint..."
if curl -sf --max-time 5 "http://${NAS_IP}:8765/health" >/dev/null; then
  echo " OK"
else
  echo " FAILED — check container logs" >&2
  exit 1
fi
