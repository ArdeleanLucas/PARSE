# parse_memory_upsert_section

**Category:** Project
**Mutability:** mutating (creates / replaces one `## Section` block in `parse-memory.md`)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Low–Medium
**Estimated Tokens:** ~220 (short) / ~470 (full)

## One-Sentence Summary
Creates or replaces a `## Section` block in `parse-memory.md` — for persisting user preferences, speaker notes, onboarding decisions, and file provenance that should survive across chat turns.

## When to Use
- Persisting a user preference the agent should remember next session ("user prefers Praat for review").
- Recording speaker-onboarding decisions (which raw files were used, what filtering was applied, language overrides).
- Storing file-provenance trails (where this annotation came from, which import run produced it).
- Capturing context decisions the agent should not have to re-discover (corpus conventions, naming rules, language family decisions).

## When NOT to Use
- For project data — cognates, borrowing flags, similarity scores, lexeme notes belong in `parse-enrichments.json`, not chat memory. Use `enrichments_write` / `lexeme_notes_write` (Comparison bucket).
- For interval-level annotation — use the Annotation-bucket tools that write `annotations/<speaker>.parse.json`.
- Without first reading the existing section via `parse_memory_read`. Upsert *replaces* the section's body — any prior content under that heading is lost. Always read, merge, write.
- Without `dryRun: true` first. The dry-run shows the rewritten file preview; user confirmation should come before live writes.

## Parameters

| Parameter | Type    | Required | Description                                                                                  | Default | Example                                  |
|-----------|---------|----------|----------------------------------------------------------------------------------------------|---------|------------------------------------------|
| section   | string  | Yes      | Heading text without leading `##`. `minLength=1`, `maxLength=200`.                           | —       | `"Speaker provenance"`                   |
| body      | string  | Yes      | Markdown body for this section. `minLength=1`, `maxLength=16000`.                            | —       | `"- Khan01: imported 2026-05-10 from..."` |
| dryRun    | boolean | Yes      | If `true`, return the rewritten file preview without writing.                                | —       | `true`                                   |

**Upsert semantics:** Other sections in `parse-memory.md` are left untouched. Only the block under the matching `## <section>` heading is replaced (or created if absent).

## Expected Output
On `dryRun: true`: returns `{ readOnly, preview, section, replacedExisting }`. `preview` is the resulting full-file content; `replacedExisting` indicates whether the section existed before.

On `dryRun: false`: rewrites `parse-memory.md` and returns `{ ok: true, section, action }` (`action` ∈ `"created"`, `"updated"`).

## Example Successful Call
Dry run (preview):
```json
{
  "section": "Speaker provenance",
  "body": "- Khan01: imported 2026-05-10 from /external/recordings/khan01_2026.wav (primary)\n- Khan02: imported 2026-05-10 from /external/recordings/khan02_2026.wav (primary)",
  "dryRun": true
}
```

Live apply:
```json
{
  "section": "Speaker provenance",
  "body": "- Khan01: ...\n- Khan02: ...",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                              |
|------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Overwrote prior section content          | Previous notes under the same heading lost                            | No auto-backup. Always (1) `parse_memory_read section="<name>"`, (2) merge with new content, (3) write.|
| Section heading drift                    | Created a duplicate section because of slight heading variation       | Headings match exactly — `"Speaker provenance"` and `"Speaker Provenance"` are different. Verify via `parse_memory_read` first. |
| Body too long                            | Validation error (`maxLength=16000`)                                  | Split the content across multiple sections, or trim before writing.                                    |
| Memory file missing                      | Tool creates the file from scratch                                    | Expected behavior — the first upsert creates the file with the requested section.                     |

## Agent Reasoning Notes
The "upsert" name is precise: insert if absent, replace if present. The replace is **whole-section**, not a delta — read the existing section before writing if you want to preserve prior content. The mandatory `dryRun` is the gate against silently destroying chat-memory context users may have built over multiple sessions. Pair with `parse_memory_read` for the canonical read-then-write pattern.

## Related Skills
- `parse_memory_read` — read the section before overwriting.
- `enrichments_write` — for cognate / borrowing / similarity data (not chat memory).
- `lexeme_notes_write` (Comparison bucket) — for per-lexeme notes (separate from chat memory).
