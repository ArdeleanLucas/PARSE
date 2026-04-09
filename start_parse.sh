#!/usr/bin/env bash
# start_parse.sh — PARSE macOS/Linux legacy launcher
# Starts the legacy thesis/review server and opens review_tool_dev.html.
# Current React development uses python/server.py + npm run dev on http://localhost:5173/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PARSE_PORT:-8766}"
SERVER_SCRIPT="python/thesis_server.py"
URL="http://localhost:${PORT}/review_tool_dev.html"

echo "Starting PARSE legacy review-tool server on port ${PORT}..."
echo "Project directory: ${SCRIPT_DIR}"
echo "Note: this launcher opens review_tool_dev.html (legacy)."
echo "For the current React UI, run python/server.py + npm run dev and open http://localhost:5173/."

if [ ! -f "${SCRIPT_DIR}/${SERVER_SCRIPT}" ]; then
    echo "ERROR: missing legacy server script: ${SCRIPT_DIR}/${SERVER_SCRIPT}" >&2
    echo "This launcher only works with the old thesis/review stack." >&2
    echo "For the current React UI, run python/server.py + npm run dev and open http://localhost:5173/." >&2
    exit 1
fi

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
python3 "${SERVER_SCRIPT}" &
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
echo "Legacy review tool is running. Press Ctrl+C to stop."

# Wait for server process
wait "${SERVER_PID}"
