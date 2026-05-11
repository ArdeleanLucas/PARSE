# enrichments_read

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~180 (short) / ~400 (full)

## One-Sentence Summary
Reads `parse-enrichments.json` (cognate sets, similarities, borrowing flags, lexeme notes) with an optional top-level key filter — the canonical inspection path for everything that lives in PARSE's enrichment file.

## When to Use
- Inspecting current cognate decisions before exporting (`export_lingpy_tsv`, `export_nexus`) or making new decisions.
- Auditing similarity scores across the project.
- Confirming borrowing flags before adjudication via the Comparison bucket tools.
- Cheap "what's in this file?" lookup before any `enrichments_write` operation.

## When NOT to Use
- For *lexeme notes only* — `lexeme_notes_read` (Comparison bucket) is a focused alternative when you only want the notes.
- For interval-level annotation data — that's `annotation_read` (Annotation bucket); enrichments are a separate file.
- For raw file inspection. The tool returns parsed JSON; for the raw text (e.g. byte-exact diff), use `read_text_preview`.

## Parameters

| Parameter | Type     | Required | Description                                                                                  | Default       | Example                              |
|-----------|----------|----------|----------------------------------------------------------------------------------------------|---------------|--------------------------------------|
| keys      | string[] | No       | Top-level keys to return (`cognate_sets`, `similarity`, `borrowing_flags`, `lexeme_notes`, `manual_overrides`, ...). Omit for full payload. | (all) | `["cognate_sets", "lexeme_notes"]` |

## Expected Output
Returns `{ readOnly, enrichments: {...} }`. The filter is **top-level only**: requested keys absent from the file are omitted from the response (not returned as `null`).

Does not mutate project state.

## Example Successful Call
Full enrichments:
```json
{}
```

Cognate sets only:
```json
{
  "keys": ["cognate_sets"]
}
```

Multiple keys:
```json
{
  "keys": ["cognate_sets", "borrowing_flags"]
}
```

## Common Failure Modes & How to Recover

| Failure                       | Symptom                                                  | Recovery                                                                                              |
|-------------------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Requested key absent          | Response omits the key (no `null`)                       | Verify the key spelling; or omit the filter to see the full payload's available keys.                  |
| Large response                | Token / payload limit                                    | Scope by `keys` to just what you need.                                                                |
| Wrong file mistaken for this  | Looking for tag data, audio metadata, etc.               | Tags live in `parse-tags.json`; this tool returns `parse-enrichments.json` only.                       |

## Agent Reasoning Notes
This is the "what's in `parse-enrichments.json`?" lookup. Most agent flows that touch enrichments should read here first to understand current state, then use `enrichments_write` for the write half. For one-off cognate exploration without persistence, `cognate_compute_preview` (Comparison bucket) is the right tool — this one reads what was *committed*; that one computes what *could be*.

## Related Skills
- `enrichments_write` — the corresponding write path.
- `lexeme_notes_read`, `lexeme_notes_write` (Comparison bucket) — focused notes path.
- `cognate_compute_preview` (Comparison bucket) — preview new cognate grouping (not yet committed).
- `read_text_preview` — raw file view if structured read isn't what you want.
