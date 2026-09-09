#!/usr/bin/env bash
# Install Docker registry mirror config (requires sudo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/etc/docker/daemon.json"
EXAMPLE="${ROOT}/docker/daemon.json.example"

if [[ ! -f "${EXAMPLE}" ]]; then
  echo "Missing ${EXAMPLE}" >&2
  exit 1
fi

# Docker daemon proxy to 127.0.0.1:12334 breaks builds when the proxy is down.
if [[ -f /etc/systemd/system/docker.service.d/http-proxy.conf ]]; then
  if ! ss -tln | grep -q ':12334 '; then
    echo "Proxy port 12334 is not listening — disabling stale Docker daemon proxy..."
    bash "${ROOT}/scripts/disable-docker-proxy.sh"
  fi
fi

sudo mkdir -p /etc/docker
if [[ -f "${TARGET}" ]]; then
  echo "Backing up existing ${TARGET} -> ${TARGET}.bak.$(date +%s)"
  sudo cp "${TARGET}" "${TARGET}.bak.$(date +%s)"
fi

sudo cp "${EXAMPLE}" "${TARGET}"
echo "Installed ${TARGET}:"
cat "${TARGET}"

echo "Restarting Docker..."
sudo systemctl daemon-reload
sudo systemctl restart docker
echo "Done. Retry: cd ${ROOT} && sudo docker compose build"
