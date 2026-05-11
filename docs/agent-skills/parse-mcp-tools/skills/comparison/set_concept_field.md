# set_concept_field

**Category:** Comparison
**Mutability:** mutating (writes `concepts.csv`)
**Supports Dry Run:** No (the schema does not expose a preview parameter)
**Complexity:** Low–Medium
**Estimated Tokens:** ~230 (short) / ~500 (full)

## One-Sentence Summary
Sets a constant string value on one column (`source_item`, `source_survey`, or `custom_order`) of multiple concept rows, selected by `id_range`, explicit `ids`, or `all=true` — the canonical bulk-attribution tool.

## When to Use
- Survey attribution: tag concepts 1–136 as `source_survey=KLQ`, 137–245 as `source_survey=JBIL`, etc.
- Bulk re-ordering with `custom_order` for compare-mode display.
- Setting `source_item` on imported concept ranges that share a common source label.
- Any time the answer is "set this column to this value on this concept ID range".

## When NOT to Use
- For per-row distinct values. The tool sets a *constant* — every selected row gets the same `value`. For per-row values, edit `concepts.csv` directly or generate the CSV externally.
- For columns outside the enum (`source_item`, `source_survey`, `custom_order`). The tool intentionally restricts to these three because they are the typical bulk-attribute targets; other columns require direct CSV editing.
- For values with commas or newlines. The schema rejects them.
- Without a clear filter scope. The `filter` requires *exactly one* of `id_range`, `ids`, or `all=true`. Don't combine them; the validator will refuse.
- Without a backup of `concepts.csv` if you're worried about the result. There is no dry-run mode and no auto-backup; the file is rewritten directly. Snapshot first if rollback may be needed.

## Parameters

| Parameter | Type   | Required | Description                                                                                              | Default | Example                              |
|-----------|--------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| column    | string | Yes      | Concept CSV column to write. Enum: `source_item`, `source_survey`, `custom_order`.                       | —       | `"source_survey"`                    |
| value     | string | Yes      | Constant value for every selected row. `maxLength=200`. Commas and newlines rejected.                    | —       | `"KLQ"`                              |
| filter    | object | Yes      | Exactly one of: `{id_range: "1-136"}`, `{ids: ["1","2","3"]}`, `{all: true}`.                            | —       | `{"id_range": "1-136"}`              |

## Expected Output
Returns `{ ok: true, column, value, rowsUpdated, filter }`. The file is rewritten directly on disk.

## Example Successful Call
Survey attribution by ID range:
```json
{
  "column": "source_survey",
  "value": "KLQ",
  "filter": {"id_range": "1-136"}
}
```

Custom order on specific IDs:
```json
{
  "column": "custom_order",
  "value": "20",
  "filter": {"ids": ["42", "43", "44"]}
}
```

Set source_item for every row:
```json
{
  "column": "source_item",
  "value": "thesis_corpus",
  "filter": {"all": true}
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Comma / newline in `value`             | Validation error                                                     | Reject values with commas; pick a single-token attribute string.                                       |
| Multiple `filter` selectors set        | Validation error                                                     | Use exactly one of `id_range`, `ids`, or `all: true`. The validator enforces this.                    |
| Wrong scope — overwrote unintended rows | Live apply touched more rows than intended                          | No auto-backup. Snapshot `concepts.csv` before bulk writes. Revert from VCS if available.             |
| Unknown column                         | Validation error                                                     | Only `source_item`, `source_survey`, `custom_order` are settable. Other columns require direct editing.|
| `id_range` malformed                   | Validation error or empty match                                      | Use `"start-end"` format (e.g. `"1-136"`) or switch to explicit `ids` array.                          |

## Agent Reasoning Notes
This is the bulk-attribution shortcut. The no-dry-run design reflects its scope: simple constant value, narrow column allowlist, mandatory filter — the surface area for surprise is small. That said, since there's no preview, *always* (1) verify the row range matches expectations (`project_context_read` for ID enumeration), (2) snapshot `concepts.csv` before non-trivial bulk writes, and (3) for production projects, consider editing `concepts.csv` in a worktree and verifying via diff before merging. For arbitrary column / per-row writes, this tool is not the right answer — go direct.

## Related Skills
- `project_context_read` — enumerate concept IDs before scoping `id_range` / `ids`.
- `read_csv_preview` (Project bucket) — inspect `concepts.csv` before / after.
- `import_tag_csv` (Project bucket) — different shape (CSV-driven tag assignment); not the same as bulk-attribute write.
