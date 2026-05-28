#!/usr/bin/env bash
# scripts/sync_review_tool.sh — Build the review_tool data from the live PARSE
# workspace and stage it into a clone of ArdeleanLucas/review_tool.
#
# Inputs (env vars; defaults shown):
#   PARSE_WORKSPACE    /home/lucas/parse-workspace
#   REVIEW_TOOL_CLONE  $HOME/gh/ardeleanlucas/review_tool
#   CONTACT_CONFIG     $PARSE_WORKSPACE/config/sil_contact_languages.json when present,
#                      otherwise <repo-root>/config/sil_contact_languages.json
#
# Flags forwarded to export_review_data.py (env-gated):
#   SKIP_AUDIO=1            → --skip-audio
#
# Does NOT auto-push. Prints next steps on success.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PARSE_WORKSPACE="${PARSE_WORKSPACE:-/home/lucas/parse-workspace}"
REVIEW_TOOL_CLONE="${REVIEW_TOOL_CLONE:-$HOME/gh/ardeleanlucas/review_tool}"

if [[ -z "${CONTACT_CONFIG:-}" && -f "$PARSE_WORKSPACE/config/sil_contact_languages.json" ]]; then
  CONTACT_CONFIG="$PARSE_WORKSPACE/config/sil_contact_languages.json"
else
  CONTACT_CONFIG="${CONTACT_CONFIG:-$REPO_ROOT/config/sil_contact_languages.json}"
fi

if [[ ! -d "$PARSE_WORKSPACE" ]]; then
  echo "error: PARSE_WORKSPACE not found: $PARSE_WORKSPACE" >&2
  echo "       Set PARSE_WORKSPACE to the live PARSE workspace directory." >&2
  exit 1
fi

if [[ ! -d "$REVIEW_TOOL_CLONE/.git" ]]; then
  echo "error: REVIEW_TOOL_CLONE is not a git clone: $REVIEW_TOOL_CLONE" >&2
  echo "       One-time setup: gh repo clone ArdeleanLucas/review_tool \"$REVIEW_TOOL_CLONE\"" >&2
  exit 1
fi

EXPORT_HELP="$(python3 "$REPO_ROOT/python/export_review_data.py" --help)"

EXPORT_ARGS=(--workspace "$PARSE_WORKSPACE" --out "$REVIEW_TOOL_CLONE")

if grep -q -- '--contact-config' <<<"$EXPORT_HELP"; then
  EXPORT_ARGS+=(--contact-config "$CONTACT_CONFIG")
fi

if [[ "${SKIP_AUDIO:-0}" == "1" ]]; then
  EXPORT_ARGS+=(--skip-audio)
fi

echo "Running: python3 $REPO_ROOT/python/export_review_data.py ${EXPORT_ARGS[*]}"
echo

SUMMARY_JSON="$(python3 "$REPO_ROOT/python/export_review_data.py" "${EXPORT_ARGS[@]}")"
printf '%s\n' "$SUMMARY_JSON"

# Soft-warn if analytical fields are all zeros (Lane B summary key; silently
# skip if export script doesn't emit analytical_coverage yet).
if [[ -n "$SUMMARY_JSON" ]]; then
  ALL_ZERO="$(SUMMARY_JSON="$SUMMARY_JSON" python3 -c '
import json, os
raw = os.environ.get("SUMMARY_JSON", "")
try:
    data = json.loads(raw)
except Exception:
    print("missing")
    raise SystemExit(0)
coverage = data.get("analytical_coverage")
if not isinstance(coverage, dict) or not coverage:
    print("missing")
    raise SystemExit(0)
print("zero" if all((v or 0) == 0 for v in coverage.values()) else "ok")
')"
  if [[ "$ALL_ZERO" == "zero" ]]; then
    echo
    echo "Reminder: analytical fields (cognate_class, similarity, arabic/persian) are"
    echo "null in this export. Run PARSE's contact_lexeme_fetcher + cognate_compute"
    echo "before re-syncing for a fully-populated review_tool."
  fi
fi

cd "$REVIEW_TOOL_CLONE"
git add -A

if git diff --cached --quiet; then
  echo
  echo "No changes to commit."
  exit 0
fi

COMMIT_DATE="$(date -u +%Y-%m-%d)"
git commit -m "$(cat <<EOF
Update review data from PARSE workspace ($COMMIT_DATE)
EOF
)"

echo
echo "Synced review_tool data."
echo "Clone: $REVIEW_TOOL_CLONE"
echo "Next:  git -C \"$REVIEW_TOOL_CLONE\" push origin main"
