#!/usr/bin/env bash
# scripts/parse-stop.sh — PARSE dev stop helper
#
# Kills the Python API server and Vite dev server on both WSL and Windows
# sides. Safe to run when nothing is running.
#
# Usage
# -----
#   scripts/parse-stop.sh
#
# Environment overrides
# ---------------------
#   PARSE_API_PORT   API server port (default: 8766)
#   PARSE_VITE_PORT  Vite dev server port (default: 5173)

set -u

: "${PARSE_API_PORT:=8766}"
: "${PARSE_VITE_PORT:=5173}"

log() { printf '[parse-stop] %s\n' "$*"; }

find_taskkill() {
  if command -v taskkill.exe >/dev/null 2>&1; then
    command -v taskkill.exe
    return
  fi
  if [ -x "/mnt/c/Windows/System32/taskkill.exe" ]; then
    echo "/mnt/c/Windows/System32/taskkill.exe"
    return
  fi
  return 1
}

log "Killing PARSE servers..."

# WSL-side
pkill -9 -f "python.*server\.py" 2>/dev/null || true
pkill -9 -f "python\.exe.*server\.py" 2>/dev/null || true
pkill -9 -f "node.*vite" 2>/dev/null || true

# Windows-side zombie python.exe cleanup
taskkill="$(find_taskkill)" || taskkill=""
if [ -n "${taskkill}" ]; then
  pids=$(
    /mnt/c/Windows/System32/wbem/WMIC.exe process where \
      "name='python.exe' and CommandLine like '%%server.py%%'" \
      get ProcessId 2>/dev/null \
      | tr -d '\r' \
      | awk 'NR>1 && $1 ~ /^[0-9]+$/ {print $1}'
  ) || true
  for pid in ${pids}; do
    "${taskkill}" /F /PID "${pid}" >/dev/null 2>&1 || true
    log "killed Windows python.exe PID ${pid}"
  done
fi

# Port-level fallback
fuser -k "${PARSE_API_PORT}/tcp" 2>/dev/null || true
fuser -k "${PARSE_VITE_PORT}/tcp" 2>/dev/null || true

log "Done."
