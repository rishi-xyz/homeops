#!/usr/bin/env bash
# Start the Next.js dev server in a dedicated session/process group and record
# the session-leader PID, so `make stop` and scripts/stop.sh can terminate the
# whole npm/next process tree instead of leaving an orphaned next-server behind.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/data/runtime/web.pid"
LOG_FILE="${HOMEOPS_WEB_LOG:-/tmp/opencode/web.log}"
mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"
cd "$ROOT/apps/web-next"
# setsid may fork to create the new session, so the child writes its own PID.
exec setsid bash -c 'echo $$ > "$1"; exec npm run dev -- --hostname 127.0.0.1 --port 3000' _ "$PID_FILE" \
  >"$LOG_FILE" 2>&1 </dev/null
