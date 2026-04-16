#!/usr/bin/env bash
# scripts/parse-run.sh — PARSE dev launcher (API + Vite)
#
# Pulls main, kills stale servers on both WSL and Windows sides, starts
# the Python API on :8766, waits for health, then starts Vite on :5173.
#
# Usage
# -----
#   scripts/parse-run.sh
#
# Environment overrides
# ---------------------
#   PARSE_PY         Python interpreter (default: python3, or $PARSE_PY if set)
#   PARSE_ROOT       Repo root (default: auto-detected from script location)
#   PARSE_API_PORT   API server port (default: 8766)
#   PARSE_VITE_PORT  Vite dev server port (default: 5173)
#   PARSE_SKIP_PULL  Set to 1 to skip `git pull` (default: 0)
#
# WSL + Windows python.exe note
# -----------------------------
# When PARSE_PY points at a Windows python.exe (e.g. a conda env on C:),
# the actual server process runs on the Windows side. WSL's pkill/fuser
# cannot signal it, which historically left zombie python.exe processes
# holding port 8766 and breaking subsequent launches. This script detects
# that case and uses taskkill.exe to clean both sides.

set -u

# ---------- Defaults ------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${PARSE_ROOT:=$(cd "${SCRIPT_DIR}/.." && pwd)}"
: "${PARSE_PY:=python3}"
: "${PARSE_API_PORT:=8766}"
: "${PARSE_VITE_PORT:=5173}"
: "${PARSE_SKIP_PULL:=0}"

API_STDOUT_LOG="/tmp/parse_api_stdout.log"
API_STDERR_LOG="/tmp/parse_api_stderr.log"
VITE_LOG="/tmp/parse_vite.log"

log() { printf '[parse-run] %s\n' "$*"; }

# ---------- Windows-aware process cleanup --------------------------------
#
# When PARSE_PY is a Windows path (/mnt/c/...), the Python process is a
# Windows process. `pkill` from WSL can only signal the WSL-side /init stub,
# not the actual Windows python.exe. Use taskkill.exe to kill the Windows
# side too.

parse_py_is_windows() {
  case "${PARSE_PY}" in
    /mnt/?/*|/mnt/?/*python.exe) return 0 ;;
    *) return 1 ;;
  esac
}

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

kill_windows_python() {
  local taskkill
  taskkill="$(find_taskkill)" || {
    log "WARNING: taskkill.exe not found — cannot clean Windows-side python.exe"
    return 0
  }
  # Kill any python.exe whose command line references server.py in our repo.
  # Use WMIC filter via tasklist + findstr + taskkill /F /PID.
  local pids
  pids=$(
    /mnt/c/Windows/System32/wbem/WMIC.exe process where \
      "name='python.exe' and CommandLine like '%%server.py%%'" \
      get ProcessId 2>/dev/null \
      | tr -d '\r' \
      | awk 'NR>1 && $1 ~ /^[0-9]+$/ {print $1}'
  ) || true
  if [ -n "${pids}" ]; then
    local pid
    for pid in ${pids}; do
      "${taskkill}" /F /PID "${pid}" >/dev/null 2>&1 || true
      log "killed Windows python.exe PID ${pid}"
    done
  fi
}

stop_servers() {
  log "Stopping stale servers..."

  # WSL-side process cleanup (covers Linux-native python, node/vite, WSL stubs)
  pkill -9 -f "python.*server\.py" 2>/dev/null || true
  pkill -9 -f "python\.exe.*server\.py" 2>/dev/null || true
  pkill -9 -f "node.*vite" 2>/dev/null || true

  # Windows-side cleanup (zombie python.exe holding :8766)
  if parse_py_is_windows; then
    kill_windows_python
  fi

  # Port-level cleanup as a last resort
  fuser -k "${PARSE_API_PORT}/tcp" 2>/dev/null || true
  fuser -k "${PARSE_VITE_PORT}/tcp" 2>/dev/null || true

  sleep 1
}

# ---------- Git pull (defensive) -----------------------------------------

pull_main() {
  if [ "${PARSE_SKIP_PULL}" = "1" ]; then
    log "PARSE_SKIP_PULL=1 — skipping git pull"
    return 0
  fi
  log "Pulling latest main..."
  (
    cd "${PARSE_ROOT}" || return 1
    # Only stash if there are actual modifications — avoids empty-stash churn.
    local stashed=0
    if ! git diff --quiet || ! git diff --cached --quiet; then
      git stash push -q -m "parse-run autostash $(date +%Y-%m-%d_%H:%M:%S)" && stashed=1
    fi
    if git pull origin main --ff-only; then
      [ "${stashed}" = "1" ] && git stash pop -q 2>/dev/null || true
      return 0
    else
      log "WARNING: git pull failed — running on current checkout"
      [ "${stashed}" = "1" ] && git stash pop -q 2>/dev/null || true
      return 0
    fi
  )
}

# ---------- Start API ----------------------------------------------------

start_api() {
  log "Starting Python API server on :${PARSE_API_PORT}..."
  # -u = unbuffered stdout (so logs appear immediately; critical for remote debugging).
  (
    cd "${PARSE_ROOT}" || exit 1
    "${PARSE_PY}" -u python/server.py \
      >"${API_STDOUT_LOG}" 2>"${API_STDERR_LOG}"
  ) &
  API_PID=$!

  log "Waiting for API on :${PARSE_API_PORT}..."
  local i
  for i in $(seq 1 24); do
    if curl -sf --max-time 2 \
      "http://127.0.0.1:${PARSE_API_PORT}/api/config" >/dev/null 2>&1; then
      log "API ready (PID: ${API_PID})"
      return 0
    fi
    sleep 0.5
  done

  log "WARNING: API did not respond after 12s — check: parse-logs api"
  return 1
}

# ---------- Start Vite ---------------------------------------------------

start_vite() {
  log "Starting Vite dev server on :${PARSE_VITE_PORT}..."
  (
    cd "${PARSE_ROOT}" || exit 1
    npx vite --host >"${VITE_LOG}" 2>&1
  ) &
  VITE_PID=$!

  local i
  for i in $(seq 1 20); do
    if curl -sf --max-time 2 \
      "http://127.0.0.1:${PARSE_VITE_PORT}/" >/dev/null 2>&1; then
      log "Vite ready (PID: ${VITE_PID})"
      return 0
    fi
    sleep 0.5
  done

  log "WARNING: Vite did not respond after 10s — check: parse-logs vite"
  return 1
}

# ---------- Banner -------------------------------------------------------

print_banner() {
  echo ""
  log "════════════════════════════════════════"
  log "  PARSE is running"
  log "  React UI:  http://localhost:${PARSE_VITE_PORT}/"
  log "  Compare:   http://localhost:${PARSE_VITE_PORT}/compare"
  log "  API:       http://localhost:${PARSE_API_PORT}/api/config"
  log "════════════════════════════════════════"
}

# ---------- Main ---------------------------------------------------------

main() {
  pull_main
  stop_servers
  start_api || return 1
  start_vite || return 1
  print_banner
}

main "$@"
