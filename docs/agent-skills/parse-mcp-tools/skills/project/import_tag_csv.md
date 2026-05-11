# import_tag_csv

**Category:** Project
**Mutability:** mutating (creates a tag entry in `parse-tags.json`)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Medium
**Estimated Tokens:** ~240 (short) / ~520 (full)

## One-Sentence Summary
Imports a CSV file as a custom tag list — matches CSV rows to project concept IDs (case-insensitive label, numeric ID, or fuzzy match with edit distance ≤ 1) — and either previews the result (`dryRun: true`) or writes the tag to `parse-tags.json` (`dryRun: false` + `tagName`).

## When to Use
- Importing an external concept list as a new tag (e.g. "Swadesh-200", "high-priority", "borrowed-from-Arabic").
- Bridging external categorizations into PARSE's tag vocabulary without manual entry of dozens / hundreds of concept IDs.
- For fuzzy-match recovery — when the CSV uses slightly different labels than the project's canonical `concept_en`.
- For programmatic tag creation from any CSV with one concept per row.

## When NOT to Use
- Without `dryRun: true` first. The `dryRun` parameter is **required** by schema. The dry-run returns matched + unmatched rows so the user can confirm coverage before committing.
- For per-concept tag *editing* — once a tag exists in `parse-tags.json`, modify it via `prepare_tag_import` (different shape: accepts an explicit `conceptIds` array) or direct file edit.
- For tag *vocabulary* inspection — read `parse-tags.json` via `read_text_preview` or `enrichments_read` (depending on where tags live in the project).
- For arbitrary CSV ingestion. The tool specifically maps rows → concept IDs; it doesn't handle multi-column attribute import.

## Parameters

| Parameter           | Type    | Required | Description                                                                                              | Default | Example                              |
|---------------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| dryRun              | boolean | Yes      | `true` previews matched / unmatched rows; `false` creates the tag (requires `tagName`).                  | —       | `true`                               |
| csvPath             | string  | No       | Path to the source CSV. `maxLength=512`.                                                                  | —       | `"imports/swadesh200.csv"`           |
| tagName             | string  | No       | Required when `dryRun: false`. `minLength=1`, `maxLength=100`.                                            | —       | `"swadesh_200"`                      |
| color               | string  | No       | Tag color hex (e.g. `"#FF6F61"`).                                                                         | —       | `"#FF6F61"`                          |
| labelColumn         | string  | No       | CSV column name to read concept labels from. `maxLength=64`.                                              | (inferred) | `"concept_en"`                    |
| matchAllVariants    | boolean | No       | When `true`, also match variant spellings of the same concept.                                            | `true`  | `true`                               |
| propagateToSpeakers | boolean | No       | When `true`, propagate the tag to every speaker's row for matched concepts.                              | `true`  | `true`                               |

## Expected Output
On `dryRun: true`: returns `{ readOnly, matched: [{ csvRow, conceptId, matchType }], unmatched: [{ csvRow }], totalRows, matchedCount, unmatchedCount }`. **The dry-run is also the only place where the tool asks for `tagName`** if not yet provided.

On `dryRun: false` (with `tagName` set): writes the new tag to `parse-tags.json` and returns `{ ok: true, tagName, conceptIds, conceptsCount }`.

## Example Successful Call
Dry run:
```json
{
  "csvPath": "imports/swadesh200.csv",
  "labelColumn": "concept_en",
  "dryRun": true
}
```

Live apply (after dry-run + confirmation):
```json
{
  "csvPath": "imports/swadesh200.csv",
  "tagName": "swadesh_200",
  "color": "#3D7EFF",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                              |
|------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Many unmatched rows                      | `unmatchedCount` high in dry-run                                     | Check `labelColumn` is correct; verify the CSV's labels against `project_context_read`'s `concepts` block. |
| Fuzzy match picked the wrong concept     | `matched` includes implausible pairings                              | Tighten matching — but the tool's match scope is fixed (label / ID / edit-distance ≤ 1). For precision, hand-curate `conceptIds` and use `prepare_tag_import` instead. |
| Live apply without `tagName`             | Tool error                                                           | `tagName` is required when `dryRun: false`. Run dry-run first to get the user to confirm a name.       |
| Existing tag overwritten                 | Live apply replaced a same-named tag's concept list                  | No auto-backup. Read `parse-tags.json` first; use unique tag names or version them (e.g. `swadesh_200_v2`). |
| CSV outside allowed roots                | Validation error                                                     | Move the CSV into the project import dir or add the parent to allowed read roots.                      |

## Agent Reasoning Notes
The two-phase dry-run-then-confirm flow is mandatory by schema design. The dry-run output is the contract: it tells the user (and agent) exactly which concepts will be tagged, which won't, and asks for a tag name. Live apply without prior dry-run is technically permitted (if `tagName` is provided) but skips the user-confirmation step — don't take that shortcut. For curated tag creation where you already know the exact concept IDs, `prepare_tag_import` is simpler.

## Related Skills
- `prepare_tag_import` — alternative when you already have the exact `conceptIds` list.
- `list_concepts_by_tag` (Comparison bucket) — verify the tag matched the expected concepts after creation.
- `rerun_lexemes_by_tag` (Comparison bucket) — downstream consumer of tags.
- `read_csv_preview` — inspect the CSV before importing.
- `project_context_read` — verify concept labels / IDs before tag creation.
