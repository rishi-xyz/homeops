#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p data/runtime /tmp/opencode
VENV="$ROOT/.venv"
[ -d "$VENV" ] || python3 -m venv "$VENV"
$VENV/bin/pip install -q -U pip >/dev/null 2>&1 || true
$VENV/bin/pip install -q -e ".[dev]" >/dev/null 2>&1 || true
$VENV/bin/python -m homeops_mcp_server.server > /tmp/opencode/mcp.log 2>&1 & echo $! > data/runtime/mcp.pid
sleep 2
$VENV/bin/uvicorn homeops_api.main:app --host 127.0.0.1 --port 8000 > /tmp/opencode/api.log 2>&1 & echo $! > data/runtime/api.pid
sleep 2
if [ -f apps/web-next/package.json ]; then
  bash "$ROOT/scripts/start-web.sh" &
else
  echo "apps/web-next/package.json not found; skipping web dev server"
fi
echo "Started. MCP: http://127.0.0.1:8001/mcp, API: http://127.0.0.1:8000, Web: http://127.0.0.1:3000"
