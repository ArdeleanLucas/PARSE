# populate_cross_survey_links

**Category:** Project
**Mutability:** mutating (writes `survey-overlap.json` when `dryRun=false`)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~250 (short) / ~650 (full)

## One-Sentence Summary
Populates `survey-overlap.json::concept_survey_links` from a reference lexeme CSV with `source`, `id`, and `lexeme` columns so cross-survey equivalents can be linked without rewriting `concepts.csv`.

## When to Use
- Linking equivalent concepts across two or more survey inventories from a reference CSV.
- Preparing Compare mode to show survey-overlap chips and source-aware grouping.
- Auditing what links would be added before any sidecar mutation.

## When NOT to Use
- To merge or delete concept rows; this tool writes sidecar links only.
- When the reference CSV has not been inspected for column names and source IDs.
- When multi-word labels need human review and `singleWordOnly=true` would skip them.

## Parameters

| Parameter | Type | Required | Description | Default | Example |
|---|---|---:|---|---|---|
| `referencePath` | string | Yes | Path to the reference lexeme CSV. | — | `"/path/to/reference.csv"` |
| `dryRun` | boolean | Yes | Preview matches/conflicts without writing when true; apply when false. | — | `true` |
| `singleWordOnly` | boolean | No | Skip labels that remain multi-word after parenthetical stripping. | `true` | `false` |
| `replace` | boolean | No | Replace existing `concept_survey_links` instead of merging new links. | `false` | `true` |

## Expected Output
Dry-run reports matched links, conflicts, skipped rows, and planned `survey-overlap.json` changes without writing. Apply writes only the survey-overlap sidecar and returns the updated summary.

## Example Successful Call
```json
{
  "referencePath": "/path/to/reference-lexemes.csv",
  "dryRun": true,
  "singleWordOnly": true,
  "replace": false
}
```

## Common Failure Modes & How to Recover

| Failure | Symptom | Recovery |
|---|---|---|
| CSV not readable | Path or sandbox validation error | Put the CSV under the workspace or allowed external read root and retry. |
| Missing columns | Tool rejects the CSV | Confirm `source`, `id`, and `lexeme` headers with `read_csv_preview`. |
| Too many skipped labels | Multi-word or ambiguous glosses skipped | Review dry-run output; rerun with `singleWordOnly=false` only after human confirmation. |
| Existing links would be overwritten | `replace=true` planned unexpectedly | Keep `replace=false` for merge mode unless intentionally rebuilding the section. |

## Agent Reasoning Notes
This tool is sidecar-only: it does not retime intervals, change annotation concept IDs, or rewrite `concepts.csv`. Always show the dry-run summary before applying and preserve `replace=false` unless the user explicitly wants a clean rebuild of `concept_survey_links`.

## Related Skills
- `read_csv_preview` — verify reference CSV columns first.
- `prepare_compare_mode` — inspect linked concepts in Compare mode.
- `project_context_read` — check current survey-overlap sidecar state.
