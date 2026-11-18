#!/usr/bin/env bash
# Start the CloudOps Sentinel API and UI for local development (POSIX).
# Usage: ./scripts/dev.sh [api-port] [ui-port]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${1:-8000}"
UI_PORT="${2:-5173}"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Virtual environment missing. Run: python3.12 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [[ ! -f "$ROOT/backend/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/backend/.env"
  echo "Created backend/.env — review secrets before shared use."
fi

cleanup() {
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${UI_PID:-}" ]] && kill "$UI_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
PYTHONPATH=. "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --reload &
API_PID=$!

cd "$ROOT/frontend"
VITE_PROXY_TARGET="http://127.0.0.1:$API_PORT" npm run dev -- --port "$UI_PORT" &
UI_PID=$!

echo "API  → http://127.0.0.1:$API_PORT/docs"
echo "UI   → http://localhost:$UI_PORT"
wait
