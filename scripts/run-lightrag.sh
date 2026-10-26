#!/usr/bin/env bash
# Start LightRAG sidecar on :9621 (working dir: backend/data/lightrag)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LR_SRC="$ROOT/backend/LightRAG"
WORKDIR="$ROOT/backend/data/lightrag"
mkdir -p "$WORKDIR/inputs" "$WORKDIR/rag_storage"

if [[ -x "$LR_SRC/.venv/bin/lightrag-server" ]]; then
  SERVER="$LR_SRC/.venv/bin/lightrag-server"
elif command -v lightrag-server >/dev/null 2>&1; then
  SERVER="$(command -v lightrag-server)"
else
  echo "lightrag-server not found. Install deps in backend/LightRAG first." >&2
  exit 127
fi

if [[ ! -f "$WORKDIR/.env" ]]; then
  if [[ -f "$LR_SRC/env.example" ]]; then
    cp "$LR_SRC/env.example" "$WORKDIR/.env"
  else
    touch "$WORKDIR/.env"
  fi
  cat >> "$WORKDIR/.env" <<EOF

# --- Odyssey overrides ---
HOST=127.0.0.1
PORT=9621
INPUT_DIR=$WORKDIR/inputs
WORKING_DIR=$WORKDIR/rag_storage
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000
LIGHTRAG_API_PREFIX=/lightrag
WEBUI_TITLE=Odyssey Knowledge Base
EOF
fi

python3 - "$WORKDIR" <<'PY'
import sys
from pathlib import Path
workdir = Path(sys.argv[1])
p = workdir / ".env"
text = p.read_text(encoding="utf-8") if p.exists() else ""
updates = {
    "HOST": "127.0.0.1",
    "PORT": "9621",
    "INPUT_DIR": str(workdir / "inputs"),
    "WORKING_DIR": str(workdir / "rag_storage"),
    "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
    "LIGHTRAG_API_PREFIX": "/lightrag",
}
# Avoid hanging on default Ollama embedding when unset
existing = {}
for line in text.splitlines():
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    existing[k.strip()] = v.strip()
if not existing.get("EMBEDDING_BINDING"):
    updates["EMBEDDING_BINDING"] = "openai"
    updates["EMBEDDING_MODEL"] = existing.get("EMBEDDING_MODEL") or "text-embedding-3-small"
    updates["EMBEDDING_DIM"] = existing.get("EMBEDDING_DIM") or "1536"
    updates["EMBEDDING_SEND_DIM"] = existing.get("EMBEDDING_SEND_DIM") or "false"
    api_key = (
        existing.get("EMBEDDING_BINDING_API_KEY")
        or existing.get("LLM_BINDING_API_KEY")
        or existing.get("OPENAI_API_KEY")
        or ""
    )
    if api_key:
        updates["EMBEDDING_BINDING_API_KEY"] = api_key
    # Prefer a real OpenAI-compatible embed host; DeepSeek LLM host is not for embeddings
    llm_host = existing.get("LLM_BINDING_HOST") or ""
    if existing.get("EMBEDDING_BINDING_HOST"):
        pass
    elif "deepseek" in llm_host.lower():
        updates["EMBEDDING_BINDING_HOST"] = "https://api.openai.com/v1"
    elif llm_host:
        updates["EMBEDDING_BINDING_HOST"] = llm_host

lines = text.splitlines()
keys_seen = set()
out = []
for line in lines:
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    k, _, _ = line.partition("=")
    k = k.strip()
    if k in updates:
        out.append(f"{k}={updates[k]}")
        keys_seen.add(k)
    else:
        out.append(line)
for k, v in updates.items():
    if k not in keys_seen:
        out.append(f"{k}={v}")
p.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

echo "LightRAG: http://localhost:9621  (proxied via Odyssey as /lightrag)"
echo "Working dir: $WORKDIR"
cd "$WORKDIR"
# Merge file-level proxy bypasses with the caller's environment. Other settings
# retain LightRAG's normal .env loading behavior.
exec python3 - "$SERVER" <<'PY_LAUNCH'
import os
import sys
from pathlib import Path
config = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    key, sep, value = line.partition("=")
    if sep and key.strip() in {"NO_PROXY", "no_proxy"}:
        config[key.strip()] = value.strip().strip(chr(34) + chr(39))
entries = ",".join(str(value or "") for value in (
    os.environ.get("NO_PROXY"), os.environ.get("no_proxy"),
    config.get("NO_PROXY"), config.get("no_proxy"),
))
if entries.strip(","):
    bypass = ",".join(dict.fromkeys(x.strip() for x in entries.split(",") if x.strip()))
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = bypass
os.execv(sys.argv[1], [sys.argv[1]])
PY_LAUNCH
