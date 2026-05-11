# revert_csv_reimport

**Category:** Project
**Mutability:** mutating (restores files from a backup directory captured by `csv_only_reimport`)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~210 (short) / ~460 (full)

## One-Sentence Summary
Restores the files captured by a `csv_only_reimport` backup for one speaker — using the manifest in the backup directory — to roll back a bad CSV re-import.

## When to Use
- Immediately after a `csv_only_reimport` that turned out to be wrong (bad source CSV, wrong concept matching, accidental run).
- For any speaker that has a `csv_only_reimport` backup under `annotations/backups/`.
- When `backupDir` is omitted — the latest `annotations/backups/*-<speaker>-csv-reimport/` is selected automatically.
- For targeted rollback — pass an explicit `backupDir` when you want a specific historical backup rather than the latest.

## When NOT to Use
- Without a prior `csv_only_reimport` backup. The tool requires a manifest-backed backup; restoring arbitrary annotation files isn't this tool's job.
- For `onboard_speaker_import` rollback — that flow doesn't capture the same backup shape. Roll back via git or by re-importing from scratch.
- For full project rollback. The tool restores per-speaker artifacts only, governed by the backup's `manifest.json`.
- Without `dryRun: true` first. Even a rollback is a write — preview the file list before committing.

## Parameters

| Parameter  | Type    | Required | Description                                                                                              | Default                | Example                                          |
|------------|---------|----------|----------------------------------------------------------------------------------------------------------|------------------------|--------------------------------------------------|
| speaker    | string  | Yes      | Speaker ID whose csv-reimport backup should be restored. `minLength=1`, `maxLength=200`.                  | —                      | `"Khan01"`                                       |
| backupDir  | string  | No       | Backup directory name or relative path under `annotations/backups/`. `maxLength=1024`.                    | (latest for speaker)   | `"20260510T192400Z-Khan01-csv-reimport"`         |
| dryRun     | boolean | No       | If `true`, preview which files would be restored without copying them.                                    | `false`                | `true`                                           |

## Expected Output
On `dryRun: true`: returns `{ readOnly, speaker, backupDir, filesToRestore: [...] }` — the manifest contents preview.

On `dryRun: false`: copies the files listed in `manifest.json` back to their project locations and returns `{ ok: true, speaker, backupDir, filesRestored }`.

**Only the filenames listed in `manifest.json` are restored** — newer files created since the backup that weren't in the original set are not touched.

## Example Successful Call
Dry run (latest backup):
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

Live restore from a specific historical backup:
```json
{
  "speaker": "Khan01",
  "backupDir": "20260508T103000Z-Khan01-csv-reimport",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| No backup found for speaker            | Tool error                                                           | Confirm `annotations/backups/` has a `*-<speaker>-csv-reimport/` directory. If not, use git for rollback.|
| Restored files older than current      | `revert` undoes work done after the backup                           | Expected behavior — the backup is a point-in-time snapshot. Re-apply newer edits manually if needed.   |
| Wrong `backupDir` chosen               | Restored too-old or too-new state                                    | Inspect `annotations/backups/` to choose the right timestamp. Backups are named `<ISO-timestamp>-<speaker>-csv-reimport`. |
| Manifest missing files                 | Some expected files not restored                                     | Only filenames listed in `manifest.json` are restored. Inspect the manifest via `read_text_preview`.   |

## Agent Reasoning Notes
This is the matching rollback path for `csv_only_reimport`. The pairing is by design: every live `csv_only_reimport` captures a manifest-backed backup with a known timestamp, and this tool consumes that exact backup format. Don't try to use it for arbitrary annotation restoration — the manifest-driven scope is what makes the rollback safe and predictable. For git-tracked rollbacks of `annotations/<speaker>.parse.json`, fall back to git instead; this tool is for the specific `csv_only_reimport` backup format only.

## Related Skills
- `csv_only_reimport` — the forward operation this tool reverts.
- `read_text_preview` — inspect `manifest.json` in a backup directory.
- `onboard_speaker_import` (Annotation bucket) — different import path with no matching revert tool (use git for rollback).
