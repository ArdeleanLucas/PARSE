# export_nexus

**Category:** Export
**Mutability:** mutating when `outputPath` is set and `dryRun: false` (writes a project NEXUS file)
**Supports Dry Run:** Yes (`dryRun: true` or omit `outputPath`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~210 (short) / ~460 (full)

## One-Sentence Summary
Exports a NEXUS cognate-character matrix for BEAST2 and other phylogenetic tools — characters are `(concept, cognate group)` pairs, values are `1` / `0` / `?` per speaker.

## When to Use
- Producing input for BEAST2 phylogenetic analysis (the typical thesis endpoint).
- For any tool that consumes NEXUS character-matrix format with binary per-taxon presence/absence data.
- Inside `export_complete_lingpy_dataset` — the workflow calls this for the NEXUS half of the bundle.
- After cognate decisions are committed in `parse-enrichments.json` — the matrix encodes them directly.

## When NOT to Use
- For wordlist-style export — use `export_lingpy_tsv`. NEXUS is a character matrix, not a wordlist; the row structure is per-taxon, not per-lexeme.
- For flat CSV consumers — use `export_annotations_csv`. NEXUS isn't a general-purpose data format; it's specifically for phylogenetic inference.
- Without committed cognate decisions. The matrix's characters are `(concept, cognate_group)` pairs from `parse-enrichments.json`; without those, the matrix has no characters.
- For the full NEXUS before previewing. Without `outputPath`, the response returns the first ~2000 characters.

## Parameters

| Parameter  | Type    | Required | Description                                                                                              | Default | Example                              |
|------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| outputPath | string  | No       | Project-relative or absolute path inside project root. Omit for preview. `minLength=1`, `maxLength=512`. | (preview only) | `"exports/lingpy/dataset.nex"`  |
| dryRun     | boolean | No       | If `true`, preview only — never writes.                                                                  | `false` | `true`                               |

## Expected Output
Preview mode: returns `{ readOnly, preview, truncated, totalChars }`. `preview` is the first ~2000 characters of the NEXUS (enough to verify the `#NEXUS` header, TAXA block, CHARACTERS block).

Write mode: writes the full NEXUS inside the project and returns `{ ok: true, outputPath, totalChars }`.

Matrix encoding:
- **Taxa** — one per speaker.
- **Characters** — one per `(concept, cognate_group)` pair from `parse-enrichments.json`.
- **States** — `1` (speaker has this cognate for this concept), `0` (speaker has a different cognate or no form), `?` (missing data — concept not annotated for this speaker).

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
  "outputPath": "exports/lingpy/dataset.nex",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                              |
|------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Empty CHARACTERS block                   | NEXUS header present but no characters                               | Cognate decisions haven't been committed. Use `cognate_compute_preview` + `enrichments_write`.        |
| Lots of `?` states                       | Many missing-data entries in matrix                                  | Speakers haven't been annotated for some concepts. This is expected for partial corpora; if undesired, complete annotations first.|
| Mismatched taxa count                    | TAXA block lists fewer / more speakers than expected                 | Verify `speakers_list` (Project bucket) — every speaker with cognate data ends up as a taxon.         |
| `outputPath` outside project             | Validation error                                                     | Use a project-relative path.                                                                          |
| Existing NEXUS silently overwritten      | Prior export at same path replaced                                   | No auto-backup. Use timestamped paths or snapshot first.                                              |
| BEAST2 rejects the matrix                | Downstream tool errors loading the file                              | Confirm BEAST2's NEXUS dialect expectations; the file is plain `#NEXUS` with `TAXA` + `CHARACTERS` blocks. |

## Agent Reasoning Notes
NEXUS is the phylogenetics-input format. The `1`/`0`/`?` encoding is the load-bearing structural property — `?` for genuinely-missing data, `0` for "has a different cognate", `1` for "has this cognate". Mis-encoding `0` vs `?` is a common silent failure that biases downstream phylogenetic inference; trust the tool's `parse-enrichments.json`-derived encoding rather than hand-editing the matrix. For the typical thesis flow, use `export_complete_lingpy_dataset` instead of this tool directly — it produces both LingPy TSV and NEXUS in one shot.

## Related Skills
- `export_lingpy_tsv` — wordlist companion.
- `export_complete_lingpy_dataset` — workflow that bundles TSV + NEXUS.
- `cognate_compute_preview` (Comparison bucket) — verify cognate grouping before export.
- `enrichments_read`, `enrichments_write` (Project bucket) — read / persist cognate decisions.
- `speakers_list` (Project bucket) — verify taxa coverage.
