#!/usr/bin/env bash
# Remove stale Docker daemon proxy (127.0.0.1:12334) when the proxy is not running.
# Symptom: proxyconnect tcp: dial tcp 127.0.0.1:12334: connect: connection refused
set -euo pipefail

PROXY_DROPIN="/etc/systemd/system/docker.service.d/http-proxy.conf"

if [[ ! -f "${PROXY_DROPIN}" ]]; then
  echo "No ${PROXY_DROPIN} — Docker proxy already disabled."
  exit 0
fi

echo "Current Docker proxy config:"
cat "${PROXY_DROPIN}"

BACKUP="${PROXY_DROPIN}.disabled.$(date +%s)"
echo "Disabling proxy: ${PROXY_DROPIN} -> ${BACKUP}"
sudo mv "${PROXY_DROPIN}" "${BACKUP}"

echo "Restarting Docker..."
sudo systemctl daemon-reload
sudo systemctl restart docker

echo "Docker proxy disabled. Verify:"
systemctl show docker --property=Environment --no-pager
