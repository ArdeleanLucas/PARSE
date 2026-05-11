# csv_only_reimport

**Category:** Project
**Mutability:** mutating (rewrites annotation + concepts + project metadata; captures mandatory backup first)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium–High
**Estimated Tokens:** ~280 (short) / ~600 (full)

## One-Sentence Summary
Re-imports an already-onboarded speaker from a refreshed Audition cue CSV (and optional comments CSV) — *without* re-accepting or copying a WAV — capturing a timestamped backup under `annotations/backups/` before rewriting the speaker's annotation files.

## When to Use
- Refreshing a speaker from a corrected Audition cue CSV after manual editing in Audition.
- Reapplying an updated comments CSV without changing the audio source.
- Iterating on CSV-only changes to a single speaker — fast vs. re-running the full onboard flow.
- When the existing primary WAV in `source_index.json` is still correct but the cue data has changed.

## When NOT to Use
- For fresh speaker imports — use `onboard_speaker_import` (Annotation bucket).
- For re-importing both WAV and CSV — use `onboard_speaker_import` (it handles both).
- For pre-aligned annotation JSON imports — use `import_processed_speaker` (Annotation bucket).
- For speakers whose primary WAV is wrong / stale — fix `source_index.json` (via `source_index_validate`) or re-import audio first, then re-import the CSV.

## Parameters

| Parameter    | Type    | Required | Description                                                                                  | Default | Example                                  |
|--------------|---------|----------|----------------------------------------------------------------------------------------------|---------|------------------------------------------|
| speaker      | string  | Yes      | Existing speaker ID to re-import. `minLength=1`, `maxLength=200`.                            | —       | `"Khan01"`                               |
| sourceCsv    | string  | Yes      | Path to the refreshed Audition cue CSV. `minLength=1`, `maxLength=1024`.                     | —       | `"imports/refreshed/Khan01.csv"`         |
| commentsCsv  | string  | No       | Optional path to the companion Audition comments CSV. `maxLength=1024`.                      | —       | `"imports/refreshed/Khan01_comments.csv"` |
| dryRun       | boolean | No       | If `true`, validate and preview the backup path without writing or re-importing.             | `false` | `true`                                   |

## Expected Output
On `dryRun: true`: returns the resolved WAV path, the timestamped backup directory that would be created, and the source CSV paths — without taking the backup or rewriting anything.

On `dryRun: false`: captures the backup at `annotations/backups/<ts>-<speaker>-csv-reimport/` (with `manifest.json`), reruns the server onboarding worker against the existing WAV, and returns `{ ok: true, speaker, backupDir, lexemesImported, commentsImported, conceptsAdded, conceptTotal, annotationPath, wavPath, csvPath, commentsCsvPath }`.

## Example Successful Call
Dry run:
```json
{
  "speaker": "Khan01",
  "sourceCsv": "imports/refreshed/Khan01.csv",
  "commentsCsv": "imports/refreshed/Khan01_comments.csv",
  "dryRun": true
}
```

Live apply (after confirmation):
```json
{
  "speaker": "Khan01",
  "sourceCsv": "imports/refreshed/Khan01.csv",
  "commentsCsv": "imports/refreshed/Khan01_comments.csv",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Speaker not onboarded                  | Tool error — no entry in `source_index.json`                         | Run `onboard_speaker_import` (Annotation bucket) first; this tool re-imports existing speakers only.   |
| CSV paths unreadable                   | Path-validation error                                                | Verify with `read_csv_preview`; place CSVs under allowed roots.                                       |
| Wrong CSV chosen — bad re-import       | Live apply rewrote annotation with wrong data                        | Use `revert_csv_reimport` to restore from the captured backup.                                        |
| Backup directory not captured          | Live apply didn't return `backupDir`                                 | Should not happen — the backup is mandatory before write. If it does, treat the re-import as unsafe and roll back via git. |
| Concepts changed unexpectedly          | `conceptsAdded` higher than expected                                 | The refreshed CSV introduced new concept rows. Verify via `read_csv_preview` before re-importing.     |

## Agent Reasoning Notes
The mandatory backup-before-write design is load-bearing — every live re-import captures a manifest-backed backup, and `revert_csv_reimport` is the matching rollback path. **Always archive the returned `backupDir` in any validation note** so the rollback is recoverable even after the chat context is lost. The tool deliberately doesn't touch the WAV — that's the whole point — so a workflow that needs new audio + new CSV must do two separate imports (or use `onboard_speaker_import` for both).

## Related Skills
- `revert_csv_reimport` — restore from the captured backup if the re-import was wrong.
- `onboard_speaker_import` (Annotation bucket) — fresh-import alternative; handles WAV + CSV together.
- `read_csv_preview` — inspect the refreshed CSV before re-importing.
- `source_index_validate` — verify / repair the speaker's `source_index.json` entry.
