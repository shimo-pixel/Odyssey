#!/usr/bin/env bash
# Run PRDS without requiring `pip install -e .`
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)/src"

# Prefer project venv (works even if not activated; avoid sudo — it drops the venv PATH)
UVICORN=""
for candidate in \
  "$ROOT/.venv/bin/uvicorn" \
  "$(pwd)/.venv/bin/uvicorn" \
  "$(command -v uvicorn 2>/dev/null || true)"
do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    UVICORN="$candidate"
    break
  fi
done

if [[ -z "$UVICORN" ]]; then
  echo "uvicorn not found. Activate the venv or install deps:" >&2
  echo "  source $ROOT/.venv/bin/activate" >&2
  echo "  cd $ROOT/backend && pip install -e '.[dev]'" >&2
  exit 127
fi

exec "$UVICORN" prds.main:app --reload --host 0.0.0.0 --port 8000 "$@"
