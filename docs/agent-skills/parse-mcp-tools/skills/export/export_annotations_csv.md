# export_annotations_csv

**Category:** Export
**Mutability:** mutating when `outputPath` is set and `dryRun: false` (writes a project CSV)
**Supports Dry Run:** Yes (`dryRun: true` or omit `outputPath`)
**Complexity:** Low
**Estimated Tokens:** ~220 (short) / ~470 (full)

## One-Sentence Summary
Exports speaker annotations to CSV — IPA, ortho, concept, timing per row — for one speaker or all speakers merged.

## When to Use
- Producing a flat CSV for external analysis (Excel, R, pandas, downstream linguistic tooling that doesn't speak ELAN/TextGrid/LingPy formats).
- Quick per-speaker spot-check via `dryRun: true` (returns the first 20 rows as a single string).
- `speaker: "all"` for a merged multi-speaker dump — every speaker's annotations in one file, with `speaker` as a discriminator column.

## When NOT to Use
- For LingPy / cognate analysis — use `export_lingpy_tsv` or the workflow `export_complete_lingpy_dataset`. The annotations CSV is a flat dump, not a cognate-aware wordlist.
- For ELAN or Praat — use `export_annotations_elan` or `export_annotations_textgrid` for the matching format.
- For NEXUS / phylogenetic input — use `export_nexus`.
- For a *full* CSV before previewing. Either set `dryRun: true` (no write, no `outputPath` needed) or omit `outputPath` (preview-only by default).

## Parameters

| Parameter  | Type    | Required | Description                                                                                              | Default       | Example                              |
|------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------------|--------------------------------------|
| speaker    | string  | No       | Speaker ID, or `"all"` for a merged multi-speaker export. `minLength=1`, `maxLength=200`.                | (defaults vary) | `"Khan01"` or `"all"`              |
| outputPath | string  | No       | Project-relative or absolute path inside project root. Omit to get a preview-only response. `minLength=1`, `maxLength=512`. | (preview only) | `"exports/annotations_all.csv"` |
| dryRun     | boolean | No       | If `true`, preview only — never writes.                                                                  | `false`       | `true`                               |

## Expected Output
Preview mode (`outputPath` omitted *or* `dryRun: true`): returns `{ readOnly, previewLines, totalLines, truncated }`. `previewLines` is the first 20 CSV lines joined into one string (header + up to 19 data rows).

Write mode (`outputPath` set and `dryRun: false`): writes the full CSV inside the project and returns `{ ok: true, outputPath, rowCount }`.

Columns: `speaker, concept_id, concept_en, start_sec, end_sec, duration_sec, ipa, ortho, source_file`.

## Example Successful Call
Per-speaker preview:
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

Merged all-speaker preview:
```json
{
  "speaker": "all",
  "dryRun": true
}
```

Live write:
```json
{
  "speaker": "all",
  "outputPath": "exports/annotations_all.csv",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `outputPath` outside project root      | Validation error                                                     | Use a project-relative path or an absolute path under the project root.                                |
| Empty / partial data                   | Few rows in preview                                                  | Verify the speaker is annotated — use `pipeline_state_read` (Advanced bucket) to confirm tier coverage.|
| Existing CSV silently overwritten      | Prior export at the same path is replaced                            | No auto-backup. Use timestamped output paths or snapshot first.                                       |
| Wrong scope (per-speaker when meant all)| Output missing some speakers                                        | Re-export with `speaker: "all"`.                                                                       |

## Agent Reasoning Notes
This is the "give me everything flat" export. Most other export tools serve more specific downstream consumers (LingPy, NEXUS, ELAN, TextGrid) — reach for this one when the downstream is generic CSV-consuming tooling. Always preview first via `dryRun: true` to confirm row count and column header before writing. The `speaker: "all"` merge is the typical thesis-export path; per-speaker exports are useful when one speaker needs to be shared with an external collaborator.

## Related Skills
- `export_lingpy_tsv` — cognate-aware wordlist TSV.
- `export_nexus` — phylogenetic character matrix.
- `export_complete_lingpy_dataset` — workflow that bundles TSV + NEXUS together.
- `export_annotations_elan`, `export_annotations_textgrid` — ELAN / Praat formats.
- `pipeline_state_read` (Advanced bucket) — confirm tier coverage before exporting.
