#!/usr/bin/env bash
# Build echo-ui:local on this Mac (cross-compiled to linux/amd64) and ship
# to the TrueNAS box. Avoids building on the server (which OOM'd previously
# with all of Ollama + Speaches + Jellyfin + the Dograh stack co-resident).
#
# Run from the echo-app repo root: ./scripts/deploy-to-truenas.sh

set -euo pipefail

SERVER=truenas_admin@192.168.70.122
TAG=echo-ui:local
REPO_ROOT="$(git rev-parse --show-toplevel)"

cd "$REPO_ROOT"

echo "==> [1/4] Build ${TAG} for linux/amd64 (QEMU emulation, ~5-10 min on Apple Silicon)"
time docker build --platform linux/amd64 --progress=plain -t "${TAG}" -f ui/Dockerfile .

echo
echo "==> [2/4] Save image to tarball (~365 MB gzipped)"
docker save "${TAG}" | gzip > /tmp/echo-ui.tar.gz
ls -lh /tmp/echo-ui.tar.gz

echo
echo "==> [3/4] Ship to ${SERVER} and load"
scp /tmp/echo-ui.tar.gz "${SERVER}:/tmp/echo-ui.tar.gz"
ssh "${SERVER}" 'gunzip -c /tmp/echo-ui.tar.gz | docker load && rm /tmp/echo-ui.tar.gz'
rm /tmp/echo-ui.tar.gz

echo
echo "==> [4/4] Recreate ui container with the new image"
ssh "${SERVER}" '
  cd /mnt/My8TBPool/AppConfig/dograh/compose
  docker compose up -d --force-recreate ui
  sleep 12
  docker compose ps ui --format "{{.Name}}\t{{.Status}}"
'

echo
echo "==> Done. Verify in browser: https://echo.pscloud.dev/"
