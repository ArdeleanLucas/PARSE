#!/usr/bin/env bash
# start_parse.sh — PARSE macOS/Linux launcher
# Starts the local server and opens the review tool in the default browser.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PARSE_PORT:-8766}"
URL="http://localhost:${PORT}/review_tool_dev.html"

echo "Starting PARSE server on port ${PORT}..."
echo "Project directory: ${SCRIPT_DIR}"

# Kill any existing process on the port
if command -v lsof >/dev/null 2>&1; then
    EXISTING_PID=$(lsof -ti tcp:"${PORT}" 2>/dev/null || true)
    if [ -n "${EXISTING_PID}" ]; then
        echo "Killing existing process on port ${PORT} (PID: ${EXISTING_PID})..."
        kill "${EXISTING_PID}" 2>/dev/null || true
        sleep 1
    fi
fi

# Start the server in the background
cd "${SCRIPT_DIR}"
python3 python/thesis_server.py &
SERVER_PID=$!
echo "Server PID: ${SERVER_PID}"

# Wait for server to be ready
echo "Waiting for server..."
for i in {1..20}; do
    if curl -sf "http://localhost:${PORT}/" >/dev/null 2>&1; then
        echo "Server ready."
        break
    fi
    sleep 0.5
done

# Open browser
echo "Opening ${URL}"
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${URL}"
elif command -v open >/dev/null 2>&1; then
    open "${URL}"
else
    echo "Cannot auto-open browser. Navigate to: ${URL}"
fi

echo ""
echo "PARSE is running. Press Ctrl+C to stop."

# Wait for server process
wait "${SERVER_PID}"
