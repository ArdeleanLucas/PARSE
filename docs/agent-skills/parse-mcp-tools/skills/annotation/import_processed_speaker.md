# import_processed_speaker

**Category:** Annotation
**Mutability:** mutating (writes WAV, annotation JSON, concepts.csv, project.json, source_index.json)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Medium–High
**Estimated Tokens:** ~280 (short) / ~590 (full)

## One-Sentence Summary
Imports a speaker from existing processed artifacts (working WAV + timestamp-aligned annotation JSON) into the PARSE workspace, preserving the annotation's alignment to the WAV — the right path when lexemes are already timestamped and you don't want PARSE to re-derive them.

## When to Use
- Migrating a speaker from a prior PARSE workspace or pipeline that already produced a working WAV plus an aligned annotation JSON.
- Importing thesis-corpus speakers whose intervals were generated externally (e.g. via Praat, Audition, or a prior PARSE) and whose timestamps are trusted.
- When you have both the WAV the timestamps are aligned to AND the annotation JSON, and want to skip the normalize → STT → forced-align chain entirely.

## When NOT to Use
- For fresh-from-tape imports where you only have a source WAV and a CSV of cues — use `onboard_speaker_import` instead. That kicks off the standard onboarding flow with downstream `audio_normalize_start` / `stt_word_level_start` work.
- When the working WAV and annotation JSON are misaligned. The tool *preserves* alignment, it does not validate it. If the annotation's interval timestamps don't match the WAV, the imported speaker will be broken.
- Without a dry-run preview. `dryRun` is required by schema — call with `true` first to see the file-copy plan, then `false` after confirming.

## Parameters

| Parameter      | Type    | Required | Description                                                                                              | Default | Example                                      |
|----------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|----------------------------------------------|
| speaker        | string  | Yes      | Speaker ID to import into the PARSE workspace. `minLength=1`, `maxLength=200`.                            | —       | `"Khan01"`                                   |
| workingWav     | string  | Yes      | Path to the processed/working WAV whose timestamps align with the annotation JSON. `minLength=1`, `maxLength=1024`. | — | `"/path/to/processed/Khan01.wav"` |
| annotationJson | string  | Yes      | Path to the timestamp-bearing annotation JSON to copy into `annotations/`. `minLength=1`, `maxLength=1024`. | — | `"/path/to/Khan01.parse.json"` |
| peaksJson      | string  | No       | Optional precomputed peaks JSON aligned to the working WAV. `maxLength=1024`.                            | —       | `"/path/to/Khan01.peaks.json"`               |
| transcriptCsv  | string  | No       | Optional legacy transcript CSV to preserve in the imported workspace. `maxLength=1024`.                  | —       | `"/path/to/Khan01.csv"`                      |
| dryRun         | boolean | Yes      | `true` previews the file-copy and metadata-write plan; `false` performs the import.                       | —       | `true`                                       |

## Expected Output
On `dryRun: true`: returns the resolved paths, planned file copies (WAV, annotation, optional peaks/CSV), planned `concepts.csv` and `project.json` updates, and `source_index.json` entry preview.

On `dryRun: false`: copies files into the workspace, writes `concepts.csv`, updates `project.json` and `source_index.json`, and preserves the annotation's timestamp alignment. Returns `{ ok: true, speaker, workspacePaths: {...} }`.

## Example Successful Call
Dry run (mandatory first step):
```json
{
  "speaker": "Khan01",
  "workingWav": "/external/processed/Khan01/Khan01.wav",
  "annotationJson": "/external/processed/Khan01/Khan01.parse.json",
  "peaksJson": "/external/processed/Khan01/Khan01.peaks.json",
  "dryRun": true
}
```

Live import:
```json
{
  "speaker": "Khan01",
  "workingWav": "/external/processed/Khan01/Khan01.wav",
  "annotationJson": "/external/processed/Khan01/Khan01.parse.json",
  "peaksJson": "/external/processed/Khan01/Khan01.peaks.json",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                              | Symptom                                                            | Recovery                                                                                                  |
|--------------------------------------|--------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Source paths outside allowed roots   | Path-validation error                                              | Add the directory to `PARSE_EXTERNAL_READ_ROOTS`, or copy the files under the project audio dir first.    |
| WAV / annotation misaligned          | Imported speaker shows intervals off-audio in the UI               | The tool doesn't validate alignment. Verify externally first; if broken, re-import with corrected source. |
| Speaker already exists               | Tool errors or overwrites the existing entry                       | This is mutating without backups — snapshot `annotations/<speaker>.parse.json` first if you might roll back.|
| Missing optional peaks JSON          | Workspace lacks waveform peaks                                     | Run `peaks_generate` after import — that produces `peaks/<speaker>.json` from the working WAV.            |

## Agent Reasoning Notes
Pick this tool over `onboard_speaker_import` when the lexeme alignment is already correct and you don't want PARSE to re-run STT / forced-align. It's a copy-and-register operation, not a compute pipeline. After import, run `peaks_generate` if `peaksJson` was not supplied so the waveform viewer works. The dry-run is mandatory by schema — never skip it; the workspace mutations include `concepts.csv`, `project.json`, and `source_index.json` updates that are non-trivial to roll back manually.

## Related Skills
- `onboard_speaker_import` — alternative for fresh-source imports without pre-aligned annotations.
- `peaks_generate` — generate `peaks/<speaker>.json` post-import if not supplied.
- `annotation_read`, `pipeline_state_read` — verify the import after completion.
