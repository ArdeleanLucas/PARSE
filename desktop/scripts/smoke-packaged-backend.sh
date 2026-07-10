#!/usr/bin/env bash
#
# End-to-end smoke test for the ASSEMBLED PARSE.app's bundled backend.
#
# This is DISTINCT from the freeze smoke that runs earlier in
# .github/workflows/desktop-macos.yml, which exercises the raw
# dist/parse-backend/ onedir BEFORE packaging. Here we drive the frozen backend
# exactly as it ships inside PARSE.app — i.e. electron-builder's copy of the
# onedir under Contents/Resources/backend/, with the afterPack +x-bit fix
# applied. Running it end-to-end proves three things at once:
#   1. the exec bit survived the extraResources copy (the guarantee afterPack.js
#      exists to make),
#   2. the frozen backend inside the packaged .app actually launches, and
#   3. /api/health responds — i.e. the shipped app's backend works.
#
# We launch the backend executable DIRECTLY (not via Electron), so no GUI or
# virtual display is needed on the runner. A FULL Electron-GUI launch — the
# renderer spawning the backend through backend-supervisor.js — is a separate
# future step that will need a virtual display.
#
# Runs from the repo root (the workflow invokes `bash desktop/scripts/...`).

set -euo pipefail

# electron-builder directories.output = build/dist (desktop/electron-builder.yml);
# the arm64 mac target lands the unpacked app under the mac-arm64 subdir. The exe
# tail matches electron-builder.yml (to: backend/parse-backend) + the PyInstaller
# onedir layout + afterPack.js's resolvePackedBackendExe().
# Absolute paths: the launch step below `cd`s into a temp project dir, so a
# relative EXE would no longer resolve. Anchor to the repo root.
REPO_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
APP="${REPO_ROOT}/desktop/build/dist/mac-arm64/PARSE.app"
EXE="${APP}/Contents/Resources/backend/parse-backend/parse-backend"

if [ ! -d "${APP}" ]; then
  echo "::error::packaged app not found at ${APP}"
  echo "--- desktop/build/dist ---"
  ls -la desktop/build/dist || true
  exit 1
fi

# (2) Assert the exec bit survived packaging — the exact guarantee the afterPack
# hook exists to make. Proving it here closes the loop end-to-end rather than
# trusting the hook ran.
if [ ! -x "${EXE}" ]; then
  echo "::error::packaged backend is missing or not executable: ${EXE}"
  ls -la "$(dirname "${EXE}")" || true
  exit 1
fi
echo "Packaged backend exec bit OK: ${EXE}"

# (2b) Assert the bundled read-only IPA model shipped inside the app (hybrid
# delivery, §9.4). The fetch step stages dist/bundled-models/<id>/ and
# electron-builder's extraResources copies it to Resources/models/<id>/. Its
# manifest.json presence proves the model actually bundled — without it, the
# backend registry would find no bundled root and the IPA stage would fall back
# to a config/HF path instead of the shipped model. The model id defaults to the
# fetch script's DEFAULT_ID and can be overridden via BUNDLED_MODEL_ID.
BUNDLED_MODEL_ID="${BUNDLED_MODEL_ID:-wav2vec2-xlsr-53-espeak-ipa}"
MODEL_MANIFEST="${APP}/Contents/Resources/models/${BUNDLED_MODEL_ID}/manifest.json"
if [ ! -f "${MODEL_MANIFEST}" ]; then
  echo "::error::bundled IPA model manifest not found in the packaged app: ${MODEL_MANIFEST}"
  echo "--- Resources/models ---"
  ls -la "${APP}/Contents/Resources/models" || true
  exit 1
fi
echo "Bundled IPA model manifest OK: ${MODEL_MANIFEST}"

# (3) Launch the packaged backend directly and poll /api/health.
PORT=8811
PROJECT_DIR="$(mktemp -d)" # fresh project dir so the desktop-mode bootstrap can initialize it
export PARSE_DESKTOP=1
export PARSE_API_PORT="${PORT}"
export PARSE_HOST=127.0.0.1

( cd "${PROJECT_DIR}" && exec "${EXE}" ) >/tmp/parse-packaged-backend-smoke.log 2>&1 &
backend_pid=$!
cleanup() {
  kill "${backend_pid}" 2>/dev/null || true
  wait "${backend_pid}" 2>/dev/null || true
}
trap cleanup EXIT

healthy=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${PORT}/api/health" >/tmp/parse-packaged-backend-health.json 2>/dev/null; then
    healthy=1
    break
  fi
  if ! kill -0 "${backend_pid}" 2>/dev/null; then
    echo "::error::packaged backend exited before serving /api/health"
    cat /tmp/parse-packaged-backend-smoke.log || true
    exit 1
  fi
  sleep 1
done

if [ "${healthy}" -ne 1 ]; then
  echo "::error::packaged backend never became healthy within 60s"
  cat /tmp/parse-packaged-backend-smoke.log || true
  exit 1
fi

echo "Health response:"
cat /tmp/parse-packaged-backend-health.json
echo
echo "Packaged app backend smoke test PASSED."
