#!/usr/bin/env bash
# run-parse.sh — WSL-only PARSE launcher
# Code lives in the repo; data lives in the workspace.
# The Python server uses cwd as the workspace root.
set -euo pipefail

REPO_DIR="/home/lucas/gh/ardeleanlucas/parse"
WORKSPACE="/home/lucas/parse-workspace"
PORT="${PARSE_PORT:-8766}"

# Ensure workspace exists
if [ ! -d "$WORKSPACE" ]; then
  echo "ERROR: workspace not found at $WORKSPACE" >&2
  exit 1
fi

if [ ! -f "$WORKSPACE/project.json" ]; then
  echo "ERROR: no project.json in $WORKSPACE" >&2
  exit 1
fi

# Kill stale processes on our ports
for p in $PORT 5173; do
  PID=$(lsof -ti tcp:"$p" 2>/dev/null || true)
  if [ -n "$PID" ]; then
    echo "Killing stale process on port $p (PID: $PID)..."
    kill "$PID" 2>/dev/null || true
    sleep 0.5
  fi
done

echo "============================================================"
echo " PARSE — WSL Launcher"
echo "  Workspace : $WORKSPACE"
echo "  Repo      : $REPO_DIR"
echo "  Backend   : http://localhost:$PORT"
echo "  Frontend  : http://localhost:5173"
echo "============================================================"

# Start Python backend (cwd = workspace = project root)
cd "$WORKSPACE"
python3 "$REPO_DIR/python/server.py" &
SERVER_PID=$!
echo "Backend PID: $SERVER_PID"

# Start Vite dev server (cwd = repo for node_modules / vite config)
cd "$REPO_DIR"
npx vite --port 5173 &
VITE_PID=$!
echo "Frontend PID: $VITE_PID"

# Trap Ctrl+C to clean up both
cleanup() {
  echo ""
  echo "Shutting down..."
  kill "$SERVER_PID" "$VITE_PID" 2>/dev/null || true
  wait "$SERVER_PID" "$VITE_PID" 2>/dev/null || true
  echo "Done."
}
trap cleanup INT TERM

echo ""
echo "Ready. Open http://localhost:5173"
echo "Press Ctrl+C to stop both servers."
wait
