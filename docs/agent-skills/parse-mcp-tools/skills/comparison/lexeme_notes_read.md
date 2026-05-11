# lexeme_notes_read

**Category:** Comparison
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~170 (short) / ~370 (full)

## One-Sentence Summary
Reads lexeme-level notes from `parse-enrichments.json`, optionally filtered by `speaker` and/or `conceptId`.

## When to Use
- Inspecting prior cognate-review or borrowing-adjudication notes for a (speaker, conceptId) pair before editing.
- Surfacing the project's accumulated commentary on a specific lexeme for the user.
- Bulk-reading notes for one speaker (omit `conceptId`) or one concept (omit `speaker`).
- As preflight before `lexeme_notes_write` — see what's already there before overwriting.

## When NOT to Use
- For non-note enrichment data (cognate sets, similarity scores, borrowing flags) — use `enrichments_read` (Project bucket) which returns the whole `parse-enrichments.json` shape or specific top-level keys.
- For raw annotation interval data — that's `annotation_read` (Annotation bucket); this is enrichments-side notes only.
- For batch export of notes across all speakers/concepts. Call this repeatedly (one per filter) or read `parse-enrichments.json` directly via `enrichments_read`.

## Parameters

| Parameter | Type   | Required | Description                                          | Default       | Example     |
|-----------|--------|----------|------------------------------------------------------|---------------|-------------|
| speaker   | string | No       | Filter to a single speaker. `minLength=1`, `maxLength=200`. | (all)         | `"Khan01"`  |
| conceptId | string | No       | Filter to a single concept. `minLength=1`, `maxLength=128`. | (all)         | `"42"`      |

## Expected Output
Returns `{ readOnly, notes: [{ speaker, conceptId, user_note, import_note }, ...], count }`. Each entry carries `user_note` (human-authored) and/or `import_note` (machine/import provenance). Empty `notes` array when no matches.

Does not mutate project state.

## Example Successful Call
Read all notes for one speaker:
```json
{
  "speaker": "Khan01"
}
```

Read notes for one (speaker, concept) pair:
```json
{
  "speaker": "Khan01",
  "conceptId": "42"
}
```

## Common Failure Modes & How to Recover

| Failure                       | Symptom              | Recovery                                                                                              |
|-------------------------------|----------------------|-------------------------------------------------------------------------------------------------------|
| No matches                    | `notes: []`          | Check filter values. Use `project_context_read` to confirm speaker / concept exist; drop the filter to broaden. |
| Need the rest of enrichments  | Notes alone insufficient | Reach for `enrichments_read` to inspect cognate sets, borrowing flags, similarities, etc.             |

## Agent Reasoning Notes
This is the focused read path for one specific class of enrichment data (lexeme notes). Use it when you only care about the notes — it's cheaper and clearer than `enrichments_read` for that case. For mixed inspection (notes + cognate sets + borrowing flags), reach for `enrichments_read` instead. Always read before writing — `lexeme_notes_write` blindly overwrites the targeted entry's `user_note` / `import_note` fields, so preserve any context you want to keep.

## Related Skills
- `lexeme_notes_write` — the corresponding write path.
- `enrichments_read` (Project bucket) — broader read of `parse-enrichments.json`.
- `annotation_read` (Annotation bucket) — interval-level data (separate from enrichments notes).
