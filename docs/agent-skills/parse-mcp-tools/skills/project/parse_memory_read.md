# parse_memory_read

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~180 (short) / ~400 (full)

## One-Sentence Summary
Reads PARSE's persistent chat memory file (`parse-memory.md`) — bounded by `maxBytes`, optionally scoped to a single `## Section` heading.

## When to Use
- At the start of a new chat session — recover speaker provenance, file origins, user preferences, prior decisions that were persisted across sessions.
- Looking up a specific decision or context block by section heading (e.g. `parse_memory_read section="Speaker provenance"`).
- Pre-write inspection before `parse_memory_upsert_section` — confirm the section's current content before overwriting.
- Auditing what's stored about a specific topic without dumping the whole memory file.

## When NOT to Use
- For project-data inspection — annotations, enrichments, source index, etc. live in their own files. Use `project_context_read` for project state and `enrichments_read` for cognate/borrowing data.
- For unbounded memory dumps. The `maxBytes` cap defaults to 262144; for huge memory files, scope by `section` instead of cranking the cap.
- For arbitrary markdown files. The tool reads `parse-memory.md` specifically; for other docs, use `read_text_preview`.

## Parameters

| Parameter | Type    | Required | Description                                                                  | Default              | Example     |
|-----------|---------|----------|------------------------------------------------------------------------------|----------------------|-------------|
| section   | string  | No       | Heading text without leading `##`. If set, returns that section only. `maxLength=200`. | (full file)         | `"Speaker provenance"` |
| maxBytes  | integer | No       | Cap on bytes returned. `minimum=512`, `maximum=262144`.                       | `262144` (full file) | `8192`      |

## Expected Output
Returns `{ readOnly, content, totalBytes, truncated, sectionsAvailable? }`. When `section` is provided, `content` is just that section's body; otherwise it's the whole file (truncated to `maxBytes` if too large).

Does not mutate project state.

## Example Successful Call
Full memory (bounded):
```json
{
  "maxBytes": 32768
}
```

Single section:
```json
{
  "section": "Speaker provenance"
}
```

## Common Failure Modes & How to Recover

| Failure                       | Symptom                                                  | Recovery                                                                                              |
|-------------------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Section not found             | Empty `content` or tool note                             | Check heading spelling. Read the whole file once to see available section headings.                   |
| Memory file missing           | Tool error                                               | `parse-memory.md` doesn't exist yet. Create the first section via `parse_memory_upsert_section`.      |
| Truncated unexpectedly        | `truncated: true`                                         | Either raise `maxBytes` (up to 262144) or scope by `section`.                                          |

## Agent Reasoning Notes
This is the persistence-recall path for chat agents working across sessions. The memory file is markdown organized by `## Section` headings — typical sections include speaker provenance, file origins, user preferences, onboarding decisions. Always read before writing (`parse_memory_upsert_section`) — overwriting a section blindly destroys context that the user may have built up over time.

## Related Skills
- `parse_memory_upsert_section` — the write half of this pair.
- `project_context_read` — different file; project state vs. chat memory.
- `read_text_preview` — generic markdown file reader; works on `parse-memory.md` too but with line-bound semantics.
