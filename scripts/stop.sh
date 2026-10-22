#!/usr/bin/env bash
# Stop the processes that scripts/dev.sh started. Kills process groups so the
# child processes of `npm run dev` (node/vite) go away too.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for pidfile in data/runtime/mcp.pid data/runtime/api.pid data/runtime/web.pid; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if [ -n "$pid" ]; then
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      sleep 1
      kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
done
# Fallback: kill by port/process patterns
pkill -f "homeops_mcp_server.server" 2>/dev/null || true
pkill -f "uvicorn homeops_api.main:app" 2>/dev/null || true
pkill -f "vite.*5173" 2>/dev/null || true
pkill -f "esbuild.*homeops" 2>/dev/null || true
echo "Stopped."
