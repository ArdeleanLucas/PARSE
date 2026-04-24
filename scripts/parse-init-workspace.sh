#!/usr/bin/env bash
# scripts/parse-init-workspace.sh — scaffold a fresh PARSE workspace directory.
#
# Creates a self-contained data directory outside the repo where PARSE keeps
# all generated state (copied audio, normalized audio, annotations, peaks,
# source_index.json, parse-memory.md, etc.). Original source files on disk
# are never mutated — chat onboarding copies them into <workspace>/audio/
# original/<speaker>/. The pipeline reads from audio/original/ and writes to
# audio/working/.
#
# Usage
# -----
#   scripts/parse-init-workspace.sh /path/to/workspace
#   scripts/parse-init-workspace.sh --concepts-csv /path/to/concepts.csv /path/to/workspace
#   scripts/parse-init-workspace.sh --project-id southern-kurdish /path/to/workspace
#
# Idempotent: running twice against the same workspace only creates what's
# missing. Never overwrites an existing project.json, parse-memory.md, or
# concepts.csv.

set -eu

PROJECT_ID=""
CONCEPTS_CSV=""
WORKSPACE=""

usage() {
  cat <<'EOF' 1>&2
Usage: parse-init-workspace.sh [--project-id ID] [--concepts-csv FILE] <workspace>

Options:
  --project-id ID        Value to write into project.json "project_id".
                         Default: basename of <workspace>.
  --concepts-csv FILE    Copy an initial concepts.csv into <workspace>.
                         Only copied if <workspace>/concepts.csv does not
                         already exist.

Positional:
  <workspace>            Absolute or relative path to the workspace directory.
                         Created if missing.
EOF
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project-id)
      [ $# -ge 2 ] || usage
      PROJECT_ID="$2"
      shift 2
      ;;
    --concepts-csv)
      [ $# -ge 2 ] || usage
      CONCEPTS_CSV="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    --)
      shift
      break
      ;;
    -*)
      printf 'unknown flag: %s\n' "$1" 1>&2
      usage
      ;;
    *)
      if [ -n "${WORKSPACE}" ]; then
        printf 'unexpected argument: %s\n' "$1" 1>&2
        usage
      fi
      WORKSPACE="$1"
      shift
      ;;
  esac
done

if [ -z "${WORKSPACE}" ]; then
  usage
fi

# Resolve to an absolute path without depending on GNU realpath.
mkdir -p "${WORKSPACE}"
WORKSPACE="$(cd "${WORKSPACE}" && pwd)"

if [ -z "${PROJECT_ID}" ]; then
  PROJECT_ID="$(basename "${WORKSPACE}")"
fi

log() { printf '[parse-init] %s\n' "$*"; }

log "Workspace: ${WORKSPACE}"
log "Project ID: ${PROJECT_ID}"

# --- Directory skeleton -------------------------------------------------------
for dir in \
  audio/original \
  audio/working \
  annotations \
  peaks \
  coarse_transcripts \
  config
do
  target="${WORKSPACE}/${dir}"
  if [ ! -d "${target}" ]; then
    mkdir -p "${target}"
    log "created ${dir}/"
  fi
done

# --- project.json -------------------------------------------------------------
project_json="${WORKSPACE}/project.json"
if [ ! -f "${project_json}" ]; then
  cat >"${project_json}" <<EOF
{
  "project_id": "${PROJECT_ID}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
  log "wrote project.json"
else
  log "project.json already exists — left alone"
fi

# --- config/sil_contact_languages.json ---------------------------------------
# Seed an empty SIL contact-language config so Borrowing detection (CLEF)
# doesn't crash with [Errno 2] on a fresh workspace. The UI's CLEF configure
# modal (Compute -> Borrowing detection (CLEF)) is what actually fills this
# file in; we just create the placeholder so the compute path has somewhere
# to write.
sil_config="${WORKSPACE}/config/sil_contact_languages.json"
if [ ! -f "${sil_config}" ]; then
  cat >"${sil_config}" <<'EOF'
{
  "_meta": {
    "primary_contact_languages": [],
    "configured_at": null,
    "schema_version": 1
  }
}
EOF
  log "wrote config/sil_contact_languages.json (empty — configure via UI)"
fi

# --- concepts.csv (optional copy) --------------------------------------------
if [ -n "${CONCEPTS_CSV}" ]; then
  if [ ! -f "${CONCEPTS_CSV}" ]; then
    log "WARNING: --concepts-csv path does not exist: ${CONCEPTS_CSV}"
  elif [ -f "${WORKSPACE}/concepts.csv" ]; then
    log "concepts.csv already exists in workspace — left alone"
  else
    cp "${CONCEPTS_CSV}" "${WORKSPACE}/concepts.csv"
    log "copied concepts.csv from ${CONCEPTS_CSV}"
  fi
fi

# --- parse-memory.md ----------------------------------------------------------
memory_path="${WORKSPACE}/parse-memory.md"
if [ ! -f "${memory_path}" ]; then
  cat >"${memory_path}" <<EOF
# PARSE chat memory

Persistent notes for PARSE AI. Maintained by \`parse_memory_upsert_section\`.
Each \`## Section\` is replaceable; other sections are left untouched.

## User preferences

(empty — PARSE AI fills this in as the user states preferences)

## Speakers

(empty — one entry per speaker as they are onboarded, noting provenance
and any notes the user shares)

## File provenance

(empty — absolute paths of originals that were copied into audio/original/
during onboarding, plus any transcription CSV origins)
EOF
  log "seeded parse-memory.md"
else
  log "parse-memory.md already exists — left alone"
fi

# --- Final guidance -----------------------------------------------------------
cat <<EOF

Workspace ready. To start PARSE against this workspace:

  PARSE_WORKSPACE_ROOT="${WORKSPACE}" \\
    PARSE_CHAT_MEMORY_PATH="${WORKSPACE}/parse-memory.md" \\
    PARSE_EXTERNAL_READ_ROOTS="/mnt/c/Users/Lucas/Thesis" \\
    bash "\$(dirname "\$0")/parse-run.sh"

Set PARSE_EXTERNAL_READ_ROOTS to the directory your original WAV/CSV files
live under (e.g. /mnt/c/Users/Lucas/Thesis on WSL). Use multiple entries
separated by ':' (':' on POSIX, ';' on Windows), or pass '*' to disable the
sandbox entirely:

  PARSE_EXTERNAL_READ_ROOTS="*"   # any absolute path is readable

PARSE AI copies the sources you point at into
${WORKSPACE}/audio/original/<speaker>/ via onboard_speaker_import — originals
are never mutated.
EOF
