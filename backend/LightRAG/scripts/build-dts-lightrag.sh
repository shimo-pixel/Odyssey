#!/usr/bin/env bash
# Build the DTS customized LightRAG image.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${DTS_LIGHTRAG_IMAGE:-dts-lightrag:latest}"

cd "$ROOT"

echo "Building ${IMAGE} from ${ROOT}/Dockerfile.dts ..."
docker build -t "${IMAGE}" -f Dockerfile.dts \
  --build-arg DOCKER_MIRROR="${DOCKER_MIRROR:-docker.m.daocloud.io}" \
  --build-arg GHCR_MIRROR="${GHCR_MIRROR:-ghcr.nju.edu.cn}" \
  --build-arg DEBIAN_MIRROR="${DEBIAN_MIRROR:-mirrors.aliyun.com}" \
  --build-arg PYPI_INDEX="${PYPI_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
  --build-arg NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}" \
  --build-arg RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://rsproxy.cn}" \
  --build-arg RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://rsproxy.cn/rustup}" \
  .

echo "Done. Start with:"
echo "  docker compose -f docker-compose.dts.yml up -d"
