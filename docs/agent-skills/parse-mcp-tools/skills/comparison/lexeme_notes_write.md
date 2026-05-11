# lexeme_notes_write

**Category:** Comparison
**Mutability:** mutating (writes the targeted entry in `parse-enrichments.json`)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~220 (short) / ~480 (full)

## One-Sentence Summary
Writes (or deletes) a single lexeme-note entry in `parse-enrichments.json` keyed by `(speaker, conceptId)`, with separate `userNote` and `importNote` fields.

## When to Use
- Recording a human-authored review comment for a specific (speaker, conceptId) pair — set `userNote`.
- Annotating machine/import provenance (which import run produced this lexeme, what flags it inherited) — set `importNote`.
- Removing a stale note entry — set `delete: true`.
- Cleaning up notes after concept-row merges or speaker re-imports.

## When NOT to Use
- For batch note operations across many (speaker, conceptId) pairs. The tool is single-entry; call it repeatedly or edit `parse-enrichments.json` directly via `enrichments_write` (Project bucket).
- For other enrichment fields (cognate sets, borrowing flags, similarities) — use `enrichments_write`.
- Without first reading the existing entry via `lexeme_notes_read`. Writing blindly overwrites `userNote` and `importNote` — preserve any context you want to keep by reading first.
- Skipping `dryRun: true`. Even though the change is small, the file is rewritten — always preview the resulting block first.

## Parameters

| Parameter  | Type    | Required | Description                                                                                  | Default | Example          |
|------------|---------|----------|----------------------------------------------------------------------------------------------|---------|------------------|
| speaker    | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                  | —       | `"Khan01"`       |
| conceptId  | string  | Yes      | Concept ID. `minLength=1`, `maxLength=128`.                                                  | —       | `"42"`           |
| userNote   | string  | No       | Human-authored note. `maxLength=4096`.                                                       | (unchanged) | `"borrowed from Arabic"` |
| importNote | string  | No       | Machine/import provenance note. `maxLength=4096`.                                            | (unchanged) | `"imported via CLEF run 2026-05-08"` |
| delete     | boolean | No       | If `true`, removes the note entry for this (speaker, conceptId). Other fields are ignored.   | `false` | `false`          |
| dryRun     | boolean | No       | If `true`, preview the resulting `lexeme_notes` block without writing `parse-enrichments.json`. | `false` | `true`           |

## Expected Output
On `dryRun: true`: returns the resulting (speaker, conceptId) entry as it would appear after the write — letting the caller confirm before committing.

On `dryRun: false`: rewrites `parse-enrichments.json` with the targeted entry created/updated/deleted, returns `{ ok: true, speaker, conceptId, action }` (`action` ∈ `"created"`, `"updated"`, `"deleted"`).

## Example Successful Call
Set a user note (dry-run):
```json
{
  "speaker": "Khan01",
  "conceptId": "42",
  "userNote": "Borrowed from Arabic; confirmed via Wiktionary",
  "dryRun": true
}
```

Delete an entry:
```json
{
  "speaker": "Khan01",
  "conceptId": "42",
  "delete": true,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Overwrote a meaningful previous note   | Live apply replaced existing `userNote` content                      | No auto-backup. Read with `lexeme_notes_read` first and preserve content explicitly when re-writing.  |
| `delete: true` with userNote / importNote set | Other field values ignored; entry deleted                     | Intentional. To update, drop `delete`. To clear one field but keep the entry, pass an empty string for that field. |
| Speaker / concept not in project       | Tool error                                                           | Verify via `project_context_read`.                                                                    |

## Agent Reasoning Notes
This is the focused write path for one specific class of enrichment data. Always pair (1) `lexeme_notes_read` to inspect the prior state, (2) `lexeme_notes_write` with `dryRun: true` to preview, (3) user confirmation, (4) `dryRun: false` to commit. For mass operations across many entries, use `enrichments_write` instead — it can replace the whole `lexeme_notes` block in one call.

## Related Skills
- `lexeme_notes_read` — read the current note before overwriting.
- `enrichments_read`, `enrichments_write` (Project bucket) — broader read/write of `parse-enrichments.json`.
