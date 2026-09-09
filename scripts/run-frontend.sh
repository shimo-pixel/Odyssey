#!/usr/bin/env bash
# Serve frontend static files on :3000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -f css/tailwind.css ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Building local Tailwind CSS…"
    if [[ ! -d node_modules ]]; then
      npm install --no-fund --no-audit
    fi
    npm run build:css
  else
    echo "Missing css/tailwind.css and npm is unavailable." >&2
    exit 1
  fi
fi

echo "Frontend: http://localhost:3000"
echo "API expected at: http://localhost:8000/api (override via window.PRDS_API_BASE)"
exec python3 -m http.server 3000
