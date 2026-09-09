#!/usr/bin/env bash
# One-shot start: LightRAG (:9621) + backend (:8000) + frontend (:3000)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/backend/data/logs"
mkdir -p "$LOG_DIR"

ready() {
  local url="$1"
  curl -sf --connect-timeout 1 --max-time 2 "$url" >/dev/null 2>&1
}

echo "==> Starting LightRAG..."
nohup "$ROOT/scripts/run-lightrag.sh" >"$LOG_DIR/lightrag.log" 2>&1 &
LR_PID=$!

echo "Waiting for LightRAG on :9621..."
LR_OK=0
for i in $(seq 1 120); do
  if ready "http://127.0.0.1:9621/health" \
    || ready "http://127.0.0.1:9621/lightrag/health" \
    || ready "http://127.0.0.1:9621/docs" \
    || ready "http://127.0.0.1:9621/lightrag/docs"; then
    echo "LightRAG is up (pid $LR_PID)"
    LR_OK=1
    break
  fi
  if ! kill -0 "$LR_PID" 2>/dev/null; then
    echo "LightRAG failed to start. See $LOG_DIR/lightrag.log" >&2
    echo "Continuing with backend + frontend (KB features may be offline)." >&2
    break
  fi
  sleep 1
done
if [[ "$LR_OK" -ne 1 ]] && kill -0 "$LR_PID" 2>/dev/null; then
  echo "LightRAG still starting (pid $LR_PID). See $LOG_DIR/lightrag.log" >&2
  echo "Continuing with backend + frontend…" >&2
fi

echo "==> Starting backend..."
nohup "$ROOT/scripts/run-backend.sh" >"$LOG_DIR/backend.log" 2>&1 &
BE_PID=$!

echo "Waiting for API on :8000..."
for i in $(seq 1 120); do
  if ready "http://127.0.0.1:8000/api/health"; then
    echo "Backend is up (pid $BE_PID)"
    break
  fi
  if ! kill -0 "$BE_PID" 2>/dev/null; then
    echo "Backend failed to start. See $LOG_DIR/backend.log" >&2
    exit 1
  fi
  if [[ "$i" -eq 120 ]]; then
    echo "Backend did not become ready in time. See $LOG_DIR/backend.log" >&2
    exit 1
  fi
  sleep 1
done

echo "==> Starting frontend..."
nohup "$ROOT/scripts/run-frontend.sh" >"$LOG_DIR/frontend.log" 2>&1 &
FE_PID=$!
sleep 0.5

cat <<EOF

Odyssey is running:
  Frontend : http://localhost:3000
  API      : http://localhost:8000/api
  LightRAG : http://localhost:8000/lightrag  (proxied; process on :9621)

Logs: $LOG_DIR/{lightrag,backend,frontend}.log
Stop: ./scripts/stop.sh
EOF
