# read_csv_preview

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~160 (short) / ~350 (full)

## One-Sentence Summary
Reads the first N rows of any CSV under the project root, returning column names, delimiter, total row count, and a sample — defaults to `concepts.csv` when no path is given.

## When to Use
- Inspecting `concepts.csv` to confirm concept ID ranges, source survey labels, custom order values before bulk operations like `set_concept_field` (Comparison bucket).
- Validating an incoming Audition cue CSV before `csv_only_reimport` or `import_tag_csv`.
- Spot-checking exported CSVs (`export_annotations_csv`) — the same tool reads any project CSV.
- Schema discovery — column names + delimiter detection on an unfamiliar CSV.

## When NOT to Use
- For full-file dumps. `maxRows` caps at 200; for larger samples read via `read_text_preview` or open the file externally.
- For non-CSV files. The tool is CSV-aware; for plain text / markdown, use `read_text_preview`.
- For paths outside the project root. The tool enforces the project-root sandbox — absolute paths outside the project are rejected.
- For binary or huge CSVs without bounding. Use `maxRows` deliberately.

## Parameters

| Parameter | Type    | Required | Description                                                                          | Default        | Example                              |
|-----------|---------|----------|--------------------------------------------------------------------------------------|----------------|--------------------------------------|
| csvPath   | string  | No       | Project-relative or absolute path inside project root. `maxLength=512`.              | `concepts.csv` | `"imports/refreshed/Khan01.csv"`     |
| maxRows   | integer | No       | Cap on returned rows. `minimum=1`, `maximum=200`.                                    | `20`           | `50`                                  |

## Expected Output
Returns `{ readOnly, csvPath, columns, delimiter, totalRows, rows: [...] }`. `rows` is a list of dicts keyed by column name, bounded by `maxRows`.

Does not mutate project state.

## Example Successful Call
Default (preview `concepts.csv`):
```json
{}
```

Specific CSV with custom row count:
```json
{
  "csvPath": "imports/refreshed/Khan01.csv",
  "maxRows": 50
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| File not found                         | Tool error                                                           | Verify the path; `csvPath` is project-relative by default.                                            |
| Path outside project root              | Validation error                                                     | Use a project-relative path, or move the file into the project.                                       |
| Wrong delimiter detection              | Columns look concatenated into one column                            | The tool auto-detects common delimiters. For unusual delimiters, the data may need preprocessing.     |
| Truncated rows                         | `rows.length == maxRows` but `totalRows > maxRows`                   | Increase `maxRows` (up to 200), or read the file with `read_text_preview` for larger chunks.          |

## Agent Reasoning Notes
This is the safe inspection path for CSVs in the project. Use it as the pre-flight before any CSV-consuming write tool (`csv_only_reimport`, `import_tag_csv`, `set_concept_field`). The `concepts.csv` default makes the common case — "show me what's in the concept list" — a single zero-arg call.

## Related Skills
- `read_text_preview` — generic text reader; works on CSVs too but without column-aware parsing.
- `csv_only_reimport` — consumes Audition cue CSVs.
- `import_tag_csv` — consumes tag-source CSVs.
- `set_concept_field` (Comparison bucket) — bulk-edit columns in `concepts.csv`.
- `export_annotations_csv` (Export bucket) — produces CSVs this tool can read back.
