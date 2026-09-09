#!/usr/bin/env bash
# Start FastAPI backend on :8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/backend/run.sh" "$@"
