# read_text_preview

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~190 (short) / ~410 (full)

## One-Sentence Summary
Reads a bounded preview of a Markdown / text file from the workspace or docs root — `.md`, `.markdown`, `.txt`, `.rst` only — with `startLine` / `maxLines` / `maxChars` bounds.

## When to Use
- Inspecting docs, plans, READMEs, agent-skill notes inside the project.
- Reading a slice of a long markdown file with explicit line bounds (`startLine: 200, maxLines: 100`).
- Pre-flight before edits to project documentation — read the relevant section first.
- Generic text inspection — when `read_csv_preview` and `parse_memory_read` don't fit.

## When NOT to Use
- For CSV files. `read_csv_preview` does CSV-aware parsing (columns, delimiter, total rows).
- For chat memory (`parse-memory.md`). `parse_memory_read` is section-aware and tailored to that file specifically.
- For binary files, code files, or unsupported extensions. The tool restricts to `.md`, `.markdown`, `.txt`, `.rst`.
- For unbounded reads. `maxLines` and `maxChars` cap the response — use them deliberately.

## Parameters

| Parameter  | Type    | Required | Description                                                              | Default | Example                              |
|------------|---------|----------|--------------------------------------------------------------------------|---------|--------------------------------------|
| path       | string  | Yes      | Project-relative or absolute path inside workspace / docs. `minLength=1`, `maxLength=1024`. | — | `"docs/architecture.md"` |
| startLine  | integer | No       | First line to return (1-indexed). `minimum=1`, `maximum=200000`.         | `1`     | `200`                                |
| maxLines   | integer | No       | Cap on returned lines. `minimum=1`, `maximum=400`.                       | `120`   | `100`                                |
| maxChars   | integer | No       | Cap on returned characters. `minimum=200`, `maximum=50000`.              | `12000` | `8000`                               |

## Expected Output
Returns `{ readOnly, path, content, startLine, endLine, totalLines, truncated }`. `content` is the text slice; `truncated: true` when bounds cut off content.

Does not mutate project state.

## Example Successful Call
First 120 lines:
```json
{
  "path": "docs/architecture.md"
}
```

Specific slice:
```json
{
  "path": "docs/architecture.md",
  "startLine": 200,
  "maxLines": 100
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Unsupported extension                  | Validation error                                                     | The tool restricts to `.md`, `.markdown`, `.txt`, `.rst`. For other formats, use a project-appropriate reader.|
| Path outside allowed roots             | Path-validation error                                                | Use a project-relative path or place the file inside the workspace / docs root.                       |
| Truncated read                         | `truncated: true`                                                    | Increase `maxLines` (up to 400) and `maxChars` (up to 50000), or paginate by `startLine`.             |
| Wrong section                          | Returned content from start of file when you wanted section X        | Use `startLine` to skip ahead, or grep externally to locate the section.                              |

## Agent Reasoning Notes
This is the generic text reader. Reach for it when no domain-specific tool fits — `read_csv_preview` for CSVs, `parse_memory_read` for `parse-memory.md`, `enrichments_read` for `parse-enrichments.json`. The line-bound semantics make it suitable for long files where you only care about a slice; use `startLine` rather than reading the whole file just to discard the prefix.

## Related Skills
- `read_csv_preview` — CSV-aware alternative.
- `parse_memory_read` — section-aware reader for `parse-memory.md`.
- `enrichments_read` — structured reader for `parse-enrichments.json`.
- `project_context_read` — overview of project state (not raw file content).
