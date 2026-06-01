# export_lingpy_tsv

**Category:** Export
**Mutability:** mutating when `outputPath` is set and `dryRun: false` (writes a project TSV)
**Supports Dry Run:** Yes (`dryRun: true` or omit `outputPath`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~210 (short) / ~460 (full)

## One-Sentence Summary
Exports a LingPy-compatible wordlist TSV from `parse-enrichments.json` + annotations — the canonical cognate-aware export for LingPy, LexStat, and similar downstream tooling.

## When to Use
- Producing input for LingPy / LexStat cognate analysis pipelines.
- For downstream phylogenetic workflows that consume LingPy wordlist format (which is most of them).
- Inside `export_complete_lingpy_dataset` — the workflow tool calls this internally.
- As a sanity check on cognate decisions: the TSV's `COGID` column reflects what's been committed in `parse-enrichments.json`.

## When NOT to Use
- For flat annotation dumps without cognate structure — use `export_annotations_csv`. LingPy TSV is column-structured around cognate analysis (ID, CONCEPT, DOCULECT, IPA, COGID, TOKENS, BORROWING) and isn't the right shape for general CSV consumers.
- For NEXUS / BEAST2 input — use `export_nexus`. NEXUS is a character matrix, not a wordlist.
- Without cognate enrichments in the project. The TSV's `COGID` column draws from `parse-enrichments.json`; without committed cognate decisions, the output will have empty or arbitrary cognate IDs.
- For the full TSV before previewing. Without `outputPath`, the response returns the first 20 lines.

## Parameters

| Parameter  | Type    | Required | Description                                                                                              | Default | Example                              |
|------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| outputPath | string  | No       | Project-relative or absolute path inside project root. Omit for preview. `minLength=1`, `maxLength=512`. | (preview only) | `"exports/lingpy/wordlist.tsv"` |
| conceptTag | string  | No       | Restrict to a concept tag (e.g. the thesis list) **and** fold survey-overlap duplicate concept ids into one canonical concept. | (none) | `"custom-sk-concept-list"` |
| consolidate | boolean | No      | Fold survey-overlap duplicate concept ids (implied when `conceptTag` is set). Response gains a `consolidation` summary. | `false` | `true` |
| dryRun     | boolean | No       | If `true`, preview only — never writes.                                                                  | `false` | `true`                               |

## Expected Output
Preview mode (`outputPath` omitted *or* `dryRun: true`): returns `{ readOnly, previewLines, totalLines, truncated, rowCount }`. `previewLines` is the first 20 TSV lines joined into one string (header + up to 19 data rows).

Write mode (`outputPath` set, `dryRun: false`): writes the full TSV inside the project and returns `{ ok: true, outputPath, rowCount }`.

Columns: `ID, CONCEPT, DOCULECT, IPA, COGID, TOKENS, BORROWING`.

## Example Successful Call
Preview:
```json
{
  "dryRun": true
}
```

Live write:
```json
{
  "outputPath": "exports/lingpy/wordlist.tsv",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `COGID` column all-empty / all-distinct | Cognate decisions haven't been committed                            | Run `cognate_compute_preview` to inspect grouping, commit decisions via the UI / `enrichments_write` (Project bucket). |
| Empty TSV                              | Few or no data rows                                                  | Verify annotations exist; use `pipeline_state_read` (Advanced bucket) for tier coverage.              |
| `BORROWING` column empty when expected  | Borrowing flags not yet set in enrichments                          | Make borrowing decisions through compare-mode / `lexeme_notes_write`, persist via `enrichments_write`.|
| `outputPath` outside project           | Validation error                                                     | Use a project-relative path or absolute under project root.                                           |
| Existing TSV silently overwritten      | Prior export at same path replaced                                   | No auto-backup. Use timestamped paths or snapshot first.                                              |

## Agent Reasoning Notes
LingPy TSV is the *cognate-aware* export. The `COGID` column is the entire point: it reflects committed cognate groupings from `parse-enrichments.json`. Without those, the TSV is structurally LingPy-shaped but analytically empty. Reach for this tool after cognate review is done; use `cognate_compute_preview` (Comparison bucket) to verify the grouping before exporting. For the standard thesis-export bundle (TSV + NEXUS together), prefer the workflow `export_complete_lingpy_dataset`.

## Related Skills
- `export_nexus` — character-matrix companion for phylogenetic tools.
- `export_complete_lingpy_dataset` — workflow that bundles TSV + NEXUS.
- `cognate_compute_preview` (Comparison bucket) — verify cognate grouping before export.
- `enrichments_read`, `enrichments_write` (Project bucket) — read / persist cognate decisions.
