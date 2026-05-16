# review_tool export

How to sync PARSE thesis-workspace data into the active
[`ArdeleanLucas/review_tool`](https://github.com/ArdeleanLucas/review_tool)
repo (the post-cutover home — NOT `review_tool_archived`).

## Purpose

`python/export_review_data.py` converts a live PARSE workspace
(`project.json`, `concepts.csv`, `parse-enrichments.json`, per-speaker
annotation JSONs, working WAVs) into the legacy `review_data.json` +
per-speaker `timestamps/*.csv` schema the existing review_tool web app
consumes. `scripts/sync_review_tool.sh` wraps that export and stages the
output into a sibling clone of the `review_tool` repo as a single commit,
ready for review and push.

## One-time setup

Clone the working `review_tool` repo locally (default location is
`$HOME/gh/ardeleanlucas/review_tool`):

```bash
gh repo clone ArdeleanLucas/review_tool $HOME/gh/ardeleanlucas/review_tool
```

Any clone path works; override with `REVIEW_TOOL_CLONE` if you keep yours
somewhere else.

## Per-export run

From the PARSE repo root:

```bash
PARSE_WORKSPACE=/home/lucas/parse-workspace \
REVIEW_TOOL_CLONE=$HOME/gh/ardeleanlucas/review_tool \
  bash scripts/sync_review_tool.sh
```

Useful env-gated flags:

- `SKIP_AUDIO=1` — emit `review_data.json` + `timestamps/` only; skip the
  ffmpeg clip materialization step (much faster while iterating on
  metadata).
- `CONTACT_CONFIG=/path/to/sil_contact_languages.json` — override the
  default config location (only forwarded if the export script advertises
  `--contact-config`).

The wrapper validates inputs, prints the export's summary JSON, stages
all changes in the clone, and commits with the message `Update review
data from PARSE workspace (YYYY-MM-DD)`. If nothing changed, it prints
`No changes to commit.` and exits cleanly.

## Cadence model

The bootstrap-once / export-and-push-many pattern:

1. **Bootstrap (one-off, refresh on concept-list change).** PARSE's
   `contact_lexeme_fetcher` populates `parse-enrichments.json` with Arabic
   and Persian lexemes via an AI provider. This costs real money per call,
   so only re-run it when the thesis concept list itself changes.
2. **Compute (when annotations change).** PARSE's `cognate_compute`
   recomputes cognate-class assignments and similarity scores. Cheap
   (seconds-to-minutes); run after any meaningful annotation pass.
3. **Export + push (every iteration).** Run `sync_review_tool.sh`. Review
   the commit it stages, then push by hand:

   ```bash
   git -C $HOME/gh/ardeleanlucas/review_tool push origin main
   ```

## Empty analytical fields warning

If `parse-enrichments.json` only contains `lexeme_notes` (i.e. the
bootstrap/compute steps haven't run yet), the export emits null/zero
defaults for `cognate_class`, `similarity`, and the Arabic/Persian columns.
The wrapper detects this and prints a reminder — this is expected
pre-bootstrap. Running `contact_lexeme_fetcher` + `cognate_compute` and
re-syncing will populate the missing fields.

## Push step

The wrapper does NOT auto-push. It stages a single commit in the clone
and stops — analogous to PARSE's "submit PRs, never merge" rule. After
reviewing the staged diff, push manually:

```bash
git -C $HOME/gh/ardeleanlucas/review_tool push origin main
```

## Out of scope

The following PARSE fields are intentionally NOT ported to the review_tool
schema (per project decision):

- `phonetic_flags`
- `verification`
- `variants`

The review_tool app does not consume these and adding them would bloat the
exported payload without buying anything.
