# export_concept_nexus

**Category:** Export
**Mutability:** mutating when `outputPath` is set and `dryRun: false` (writes a project NEXUS file)
**Supports Dry Run:** Yes (`dryRun: true` or omit `outputPath`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~230 (short) / ~480 (full)

## One-Sentence Summary
Exports a consolidated NEXUS cognate-character matrix using the same selection model as `export_concept_appendix_md` — `tagId` / `conceptIds` / `speakers` — so the phylogenetic matrix matches the data a reviewer verifies in the concept appendix.

## When to Use
- Producing a BEAST2 / phylogenetic NEXUS for a **curated** concept set or a **taxon subset** — e.g. the thesis tag restricted to specific speakers — rather than the whole project.
- When you want the matrix to mirror exactly what `export_concept_appendix_md` shows for the same `conceptIds` + `speakers`.
- When you need the **full** NEXUS back from a preview (no `outputPath`), without the 2000-char truncation `export_nexus` applies.
- After cognate decisions are committed in `parse-enrichments.json` — the matrix encodes them directly.

## When NOT to Use
- For a quick whole-project / whole-tag NEXUS with no taxon subsetting — `export_nexus` is the simpler tool (it also supports `conceptTag` / `consolidate`).
- For the per-concept forms-and-decisions document a human reads — use `export_concept_appendix_md` (markdown, not a character matrix).
- For wordlist-style export — use `export_lingpy_tsv`.
- Without committed cognate decisions. The matrix's characters are `(concept, cognate_group)` pairs from `parse-enrichments.json`; without those, there are no characters.

## Parameters

| Parameter   | Type     | Required | Description                                                                                                                                  | Default | Example |
|-------------|----------|----------|----------------------------------------------------------------------------------------------------------------------------------------------|---------|---------|
| tagId       | string   | No       | parse-tags.json tag id to restrict concepts by (e.g. the thesis tag). Ignored when `conceptIds` is provided. `minLength=1`, `maxLength=200`. | (none)  | `"custom-sk-concept-list"` |
| conceptIds  | string[] | No       | Explicit concept-id subset (concepts.csv ids). When provided, covers exactly these concepts instead of the whole tag.                          | (use `tagId`) | `["1","16","52"]` |
| speakers    | string[] | No       | Speaker subset; project.json order is preserved. Cognate columns that go all-absent for the retained speakers are dropped; `?` cells are kept. | (all)   | `["Fail01","Kalh01"]` |
| outputPath  | string   | No       | Project-relative or absolute path inside project root. Omit for preview. `minLength=1`, `maxLength=512`.                                       | (preview only) | `"exports/beast2/matrix.nex"` |
| dryRun      | boolean  | No       | If `true`, preview only — never writes.                                                                                                       | `false` | `true`  |

## Expected Output
Preview mode (no `outputPath` / `dryRun: true`): returns `{ readOnly, previewOnly, nexus, totalChars, consolidated, tagId, consolidation, warnings, beast2_ready }`. Unlike `export_nexus`, `nexus` is the **full** matrix text, not a truncated preview.

Write mode: writes the full NEXUS inside the project and returns `{ success: true, outputPath, totalChars, consolidated, consolidation, warnings, beast2_ready }`.

`consolidation` summarises `{ concept_count, character_count, collapsed_groups, needs_recluster_groups }`.

Matrix encoding (identical to `export_nexus`):
- **Taxa** — one per retained speaker.
- **Characters** — one per `(canonical concept, cognate_group)` pair; survey-overlap duplicate ids are folded.
- **States** — `1` (speaker has this cognate), `0` (has a different cognate / no form for an attested concept), `?` (missing — concept not annotated for this speaker).

## Example Successful Call
Preview the thesis tag for a nine-speaker subset:
```json
{
  "tagId": "custom-sk-concept-list",
  "speakers": ["Fail01","Saha01","Mand01","Qasr01","Kalh01","Khan02","Qorv01","Fail03","Badr01"],
  "dryRun": true
}
```

Write an exact curated concept set:
```json
{
  "conceptIds": ["1","16","52"],
  "outputPath": "exports/beast2/matrix.nex"
}
```

## Common Failure Modes & How to Recover

| Failure                              | Symptom                                                  | Recovery                                                                                          |
|--------------------------------------|----------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| Empty / tiny CHARACTERS block        | NEXUS header present but few/no characters               | Cognate decisions not committed, or the tag/conceptIds match nothing. Check `list_concepts_by_tag` and `enrichments_read`. |
| Fewer taxa than expected             | TAXA block missing speakers you passed                   | Unknown speakers are ignored with a warning; confirm names against `speakers_list`.               |
| Unexpectedly dropped characters      | NCHAR lower than the full-project matrix                 | Expected when `speakers` is a subset — columns all-absent for the retained taxa are removed (`?` is preserved). |
| `needs_recluster` warnings           | A concept's per-id cognate letters differ                | Survey-overlap ids whose letters aren't byte-identical are kept separate, not silently merged.    |
| `outputPath` outside project         | Validation error                                         | Use a project-relative path.                                                                      |

## Agent Reasoning Notes
This is the NEXUS sibling of `export_concept_appendix_md`: pass it the **same** `tagId` / `conceptIds` / `speakers` you exported the appendix with, and the character matrix will correspond cell-for-cell to that appendix. Prefer it over `export_nexus` whenever the export is a curated subset (specific concepts or a taxon set) or when you need the full untruncated NEXUS from a preview. The `1` / `0` / `?` encoding is load-bearing — trust the `parse-enrichments.json`-derived states rather than hand-editing the matrix.

## Related Skills
- `export_concept_appendix_md` — the human-readable per-concept companion with the same selection model.
- `export_nexus` — simpler whole-project / whole-tag NEXUS (truncated preview, no taxon subset).
- `export_complete_lingpy_dataset` — workflow that bundles TSV + NEXUS.
- `cognate_compute_preview` (Comparison bucket) — verify cognate grouping before export.
- `enrichments_read`, `enrichments_write` (Project bucket) — read / persist cognate decisions.
