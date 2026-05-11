# enrichments_write

**Category:** Project
**Mutability:** mutating (merges into or replaces `parse-enrichments.json`)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~240 (short) / ~520 (full)

## One-Sentence Summary
Writes keys into `parse-enrichments.json` — shallow-merges by default, or fully replaces if `merge: false` — for cognate sets, borrowing flags, similarity scores, lexeme notes, and manual overrides.

## When to Use
- Persisting cognate decisions after `cognate_compute_preview` review.
- Committing borrowing flags (`borrowing_flags`) after adjudication in compare mode.
- Storing similarity scores from external computation that should be available to downstream exports.
- Bulk update of multiple enrichment fields at once (single call with a complex `enrichments` object).
- Full replacement (rare) when migrating from an external enrichments store — `merge: false`.

## When NOT to Use
- For single lexeme notes — `lexeme_notes_write` (Comparison bucket) is the focused alternative.
- Without first reading the current state. Shallow merge means *top-level keys* in your payload replace top-level keys in the file. If you want to add ONE cognate set without losing others, read the existing `cognate_sets` block first, modify it, and write the whole modified block.
- Without `dryRun: true` first. The file holds load-bearing data (cognate sets, borrowing flags) — always preview the resulting top-level keys before writing.
- For arbitrary JSON without schema awareness. The file has a known shape (`cognate_sets`, `similarity`, `borrowing_flags`, `lexeme_notes`, `manual_overrides`, ...); writing arbitrary keys works but downstream tools won't consume them.

## Parameters

| Parameter   | Type    | Required | Description                                                                                              | Default | Example                              |
|-------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| enrichments | object  | Yes      | Object to merge into (or replace) `parse-enrichments.json`.                                              | —       | `{"cognate_sets": {"42": {"1": ["Khan01"]}}}` |
| merge       | boolean | No       | `true` shallow-merges top-level keys; `false` replaces the whole file.                                   | `true`  | `true`                               |
| dryRun      | boolean | No       | If `true`, preview the resulting top-level keys without writing.                                          | `false` | `true`                               |

**Shallow merge semantics:** Top-level keys in `enrichments` replace top-level keys in the file. Nested structure under those keys is NOT merged — the new top-level value wins entirely.

## Expected Output
On `dryRun: true`: returns `{ readOnly, incomingKeys, resultingKeys, merge, path }` — preview of which keys would end up in the file.

On `dryRun: false`: rewrites `parse-enrichments.json` and returns `{ ok: true, keysWritten, merge, path }`.

## Example Successful Call
Dry run, shallow merge:
```json
{
  "enrichments": {
    "cognate_sets": {
      "42": {"1": ["Khan01", "Khan02"]}
    },
    "borrowing_flags": {
      "42": {"Khan03": true}
    }
  },
  "merge": true,
  "dryRun": true
}
```

Live merge:
```json
{
  "enrichments": {
    "cognate_sets": {
      "42": {"1": ["Khan01", "Khan02"]}
    }
  },
  "merge": true,
  "dryRun": false
}
```

Full replacement (rare):
```json
{
  "enrichments": { "cognate_sets": {...}, "similarity": {...}, "borrowing_flags": {...} },
  "merge": false,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                              |
|------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Shallow merge dropped nested data        | Wrote `cognate_sets: {42: {...}}` and lost `cognate_sets: {41: {...}}` | Read existing `cognate_sets` first, modify in place, write the whole block. Shallow merge doesn't deep-merge. |
| `merge: false` wiped everything          | Whole file replaced with partial payload                             | No auto-backup. Use git to restore, or rebuild from scratch.                                          |
| Unknown / typo'd top-level key           | New key appears but downstream tools ignore it                       | Use canonical keys (`cognate_sets`, `similarity`, `borrowing_flags`, `lexeme_notes`, `manual_overrides`). |
| Schema mismatch under a key              | `enrichments_write` accepts the payload but `cognate_compute_preview` errors later | The tool doesn't validate inner schema. Match the existing shape; inspect via `enrichments_read` first. |

## Agent Reasoning Notes
The shallow-merge semantics is the load-bearing gotcha — it's not deep-merge. For modifying one entry inside `cognate_sets`, the right pattern is (1) `enrichments_read keys=["cognate_sets"]`, (2) modify the returned `cognate_sets` block, (3) write the *whole modified block* back via this tool with `merge: true`. The `merge: true` mechanic only protects unrelated top-level keys (e.g. `lexeme_notes` won't be touched if you only write `cognate_sets`).

Always `dryRun: true` first. Always git-commit before bulk writes — there's no auto-backup, and `parse-enrichments.json` carries decisions that may have taken hours of human review to produce.

## Related Skills
- `enrichments_read` — read existing state before writing (mandatory for safe shallow-merge).
- `lexeme_notes_write` (Comparison bucket) — focused single-entry alternative.
- `cognate_compute_preview` (Comparison bucket) — preview cognate grouping before persisting.
- `read_text_preview` — raw file view of `parse-enrichments.json`.
