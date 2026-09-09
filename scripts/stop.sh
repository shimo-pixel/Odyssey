#!/usr/bin/env bash
# Stop PRDS backend (:8000), frontend (:3000), and LightRAG (:9621)
set -euo pipefail

stop_by_pattern() {
  local pattern="$1"
  local label="$2"
  local pids
  pids="$(pgrep -f "$pattern" 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "$label: not running"
    return 0
  fi
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 0.4
  pids="$(pgrep -f "$pattern" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
  echo "$label: stopped"
}

free_port() {
  local port="$1"
  local pids
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    return 0
  fi
  pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.3
    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

stop_by_pattern 'uvicorn prds.main:app' 'backend (uvicorn)'
stop_by_pattern 'http.server 3000' 'frontend (http.server)'
stop_by_pattern 'lightrag-server' 'lightrag-server'
stop_by_pattern 'lightrag-gunicorn' 'lightrag-gunicorn'

free_port 8000
free_port 3000
free_port 9621

echo "Done."
