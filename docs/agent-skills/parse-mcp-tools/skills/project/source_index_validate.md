# source_index_validate

**Category:** Project
**Mutability:** mutating in `mode: "full"` with `outputPath` set and `dryRun: false` (writes `source_index.json`)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~250 (short) / ~530 (full)

## One-Sentence Summary
Validates a speaker manifest entry or a full manifest against the SourceIndex schema — two modes: `speaker` (validate + transform one entry) or `full` (validate + build the complete `source_index.json`, optionally writing it).

## When to Use
- Repairing a malformed `source_index.json` entry that's preventing onboarding / re-import from finding a speaker.
- Validating an external manifest before importing it as the project's `source_index.json`.
- Diagnosing why `csv_only_reimport` says "speaker not registered" — run `mode: "speaker"` against the entry to see schema errors.
- Bulk-rebuilding `source_index.json` from a known-good manifest source (`mode: "full"`).

## When NOT to Use
- For one-off speaker-registration writes — use `onboard_speaker_import` (Annotation bucket). It registers entries automatically and is the safer path for new sources.
- For arbitrary JSON validation. The tool is specific to the SourceIndex schema; for general JSON validation, use external tooling.
- To inspect the file's content. Use `read_text_preview` for that.
- Without a clear understanding of which mode is appropriate. `mode: "speaker"` validates ONE entry; `mode: "full"` works on the whole `speakers` map.

## Parameters

| Parameter   | Type    | Required | Description                                                                                              | Default     | Example                              |
|-------------|---------|----------|----------------------------------------------------------------------------------------------------------|-------------|--------------------------------------|
| mode        | string  | No       | `speaker` validates + transforms one entry; `full` validates + builds the complete `source_index.json`.   | `"speaker"` | `"full"`                             |
| speakerId   | string  | Yes for `mode: "speaker"` | Speaker ID. `minLength=1`, `maxLength=200`.                                                | —           | `"Khan01"`                           |
| speakerData | object  | Yes for `mode: "speaker"` | Speaker manifest entry to validate.                                                       | —           | `{"sources": [...], ...}`            |
| manifest    | object  | Yes for `mode: "full"` | Full manifest with top-level `speakers` key.                                                  | —           | `{"speakers": {"Khan01": {...}, ...}}` |
| outputPath  | string  | No (only meaningful with `mode: "full"`) | Where to write `source_index.json`. `minLength=1`, `maxLength=512`.            | —           | `"source_index.json"`                |
| dryRun      | boolean | No       | If `true`, never writes `outputPath` even when provided. Returns the validated payload only.             | `false`     | `true`                               |

## Expected Output
**`mode: "speaker"`**: returns `{ readOnly, mode: "speaker", speakerId, valid, errors: [...], transformed: {...} }`. `errors` is empty when valid; `transformed` is the schema-compliant version of the input.

**`mode: "full"` + `dryRun: true`** (or no `outputPath`): returns `{ readOnly, mode: "full", valid, errors: [...], built: {...} }`. `built` is the constructed manifest.

**`mode: "full"` + `outputPath` + `dryRun: false`**: writes `source_index.json` and returns `{ ok: true, mode: "full", path, valid }`.

## Example Successful Call
Validate one speaker entry:
```json
{
  "mode": "speaker",
  "speakerId": "Khan01",
  "speakerData": {
    "sources": [
      {"path": "audio/original/Khan01/Khan01.wav", "is_primary": true}
    ]
  }
}
```

Build full manifest, dry-run preview:
```json
{
  "mode": "full",
  "manifest": {
    "speakers": {
      "Khan01": {"sources": [{"path": "audio/original/Khan01/Khan01.wav", "is_primary": true}]},
      "Khan02": {"sources": [{"path": "audio/original/Khan02/Khan02.wav", "is_primary": true}]}
    }
  },
  "outputPath": "source_index.json",
  "dryRun": true
}
```

Build and write:
```json
{
  "mode": "full",
  "manifest": { ... },
  "outputPath": "source_index.json",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `valid: false` with errors             | `errors` array describes schema violations                            | Fix the input per the errors, re-validate. Common issues: missing `is_primary` on multi-source speakers, paths outside project. |
| Wrong mode for the input shape         | Schema errors that don't match the input                              | `mode: "speaker"` expects a single entry, not a `{speakers: {...}}` wrapper. `mode: "full"` expects the wrapper. |
| Overwrote a known-good `source_index.json` | `outputPath` set with a partial manifest replaced the full one    | No auto-backup. Snapshot or use git before any `mode: "full"` write.                                  |
| Speaker fields missing from output     | Validated input was already incomplete; the output is too             | The tool validates and transforms — it doesn't invent missing fields. Provide the complete entry.      |

## Agent Reasoning Notes
This is the schema-enforcement gate for `source_index.json`. Most agents won't need it — `onboard_speaker_import` and `csv_only_reimport` handle registration automatically. Reach for `source_index_validate` when (1) something has gone wrong with the manifest (typically after manual editing), (2) you're bulk-rebuilding from an external source, or (3) you want to validate a candidate entry before committing it. The `speaker` vs `full` mode distinction is load-bearing — pick `speaker` for one-entry validation, `full` for whole-file operations.

## Related Skills
- `onboard_speaker_import` (Annotation bucket) — the canonical write path for new sources.
- `csv_only_reimport` — consumes existing `source_index.json` entries.
- `read_text_preview` — inspect the current `source_index.json` before validating.
- `speakers_list` — enumerate speakers currently visible to the project.
