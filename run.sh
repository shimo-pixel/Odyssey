#!/usr/bin/env bash
# Run PRDS without requiring `pip install -e .`
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)/src"
exec uvicorn prds.main:app --reload --host 0.0.0.0 --port 8000 "$@"
