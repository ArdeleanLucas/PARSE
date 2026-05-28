# migrate_concept_suffix_pollution

**Category:** Project
**Mutability:** mutating (live apply rewrites workspace data and creates backups)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** High
**Estimated Tokens:** ~350 (short) / ~900 (full)

## One-Sentence Summary
Dry-runs, applies, or verifies the PARSE concept-identity migration that canonicalizes stored variant suffix pollution and collapses same-slot clarifier sibling rows with backup-backed rewrites.

## When to Use
- Before or after a concept-identity migration of a PARSE workspace.
- To verify that `concepts.csv`, annotations, tags, and survey sidecars no longer point at suffix-polluted IDs.
- To collapse same `(source_survey, source_item, strip_clarifier(concept_en))` sibling rows while preserving provenance in δ-format notes.

## When NOT to Use
- For ordinary concept editing during annotation; use UI/API concept tools instead.
- While the PARSE backend/UI may be writing to the same workspace.
- Without a dry run and human review of planned rewrites.

## Parameters

| Parameter | Type | Required | Description | Default | Example |
|---|---|---:|---|---|---|
| `workspace` | string | Yes | PARSE workspace root containing `concepts.csv`. | — | `"/path/to/parse-workspace"` |
| `dryRun` | boolean | No | Preview migration only; no writes or backups. | `false` | `true` |
| `verifyOnly` | boolean | No | Run verification/audit checks without migration writes. | `false` | `true` |

## Expected Output
Dry-run returns merge-map counts, planned annotation/tag/survey rewrites, clarifier-collapse counts, and `backups: 0`. Live apply returns the same counters after writing backups and atomically replacing changed files. Verify-only reports hard post-migration violations and data-audit findings without rewriting.

## Example Successful Call
Dry-run first:
```json
{
  "workspace": "/path/to/parse-workspace",
  "dryRun": true
}
```

Verification after apply:
```json
{
  "workspace": "/path/to/parse-workspace",
  "verifyOnly": true
}
```

## Common Failure Modes & How to Recover

| Failure | Symptom | Recovery |
|---|---|---|
| Active writer race | Backend/UI still running against the workspace | Stop PARSE writers before live apply; rerun dry-run after the workspace is quiet. |
| Unexpected merge map | Planned rows do not match the intended source slots | Do not apply; inspect `concepts.csv`, annotations, and survey sidecars first. |
| Verify-only reports residual audits | Non-zero cross-survey/text-vs-label findings | Distinguish hard migration violations from pre-existing data-quality notes before calling failure. |
| Bad live apply | Workspace state wrong after mutation | Restore from the timestamped backups emitted in the result. |

## Agent Reasoning Notes
Treat `dryRun=true` as mandatory. A live apply mutates `concepts.csv`, annotation JSON, `parse-tags.json`, `survey-overlap.json`, and the compare-notes mirror when clarifier rows collapse. Always record the backup suffix/path list and rerun `verifyOnly` or a second idempotence dry-run after applying.

## Related Skills
- `read_csv_preview` — inspect concept rows before migration.
- `export_review_data` — verify reviewer export after migration.
- `project_context_read` — confirm workspace state before and after.
