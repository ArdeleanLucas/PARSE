# onboard_speaker_import

**Category:** Annotation
**Mutability:** mutating (copies WAV, scaffolds annotation, appends to `source_index.json`)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Medium–High
**Estimated Tokens:** ~310 (short) / ~660 (full)

## One-Sentence Summary
Imports a speaker's audio source from disk (and optional transcription CSV) into `audio/original/<speaker>/`, scaffolds the annotation record on first import, and appends the source to `source_index.json` — the canonical fresh-onboarding entry point.

## When to Use
- For brand-new speakers being added to a project. First call creates the speaker; subsequent calls add additional audio sources.
- Multi-source speakers: call this tool once per audio source (multiple WAVs for the same speaker). First call defaults to `isPrimary: true`; subsequent calls default to `isPrimary: false`.
- Importing from `PARSE_EXTERNAL_READ_ROOTS` (set to `*` for no sandbox) or paths inside the project `audio/` directory.

## When NOT to Use
- When you have pre-aligned annotation artifacts (working WAV + annotation JSON) — use `import_processed_speaker` instead. That one preserves alignment without re-running the pipeline.
- For multi-WAV speakers expecting auto-aligned annotations across all sources — PARSE does *not* yet auto-align multiple WAVs across a shared virtual timeline. The response will flag `virtualTimelineRequired: true`; annotation spanning multiple WAVs must be coordinated manually or deferred.
- Without a dry-run preview. `dryRun` is required by schema — call with `true` first to inspect planned copies and registrations.

## Parameters

| Parameter | Type    | Required | Description                                                                                                       | Default                  | Example                                |
|-----------|---------|----------|-------------------------------------------------------------------------------------------------------------------|--------------------------|----------------------------------------|
| speaker   | string  | Yes      | Speaker ID to create or extend. `minLength=1`, `maxLength=200`.                                                   | —                        | `"Khan01"`                             |
| sourceWav | string  | Yes      | Absolute or project-relative path to the source audio. `minLength=1`, `maxLength=1024`.                            | —                        | `"/external/recordings/Khan01.wav"`    |
| sourceCsv | string  | No       | Optional transcript CSV to store alongside the imported source. `maxLength=1024`.                                  | —                        | `"/external/recordings/Khan01.csv"`    |
| isPrimary | boolean | No       | Flag this WAV as the speaker's primary source.                                                                    | `true` if no existing sources; `false` otherwise | `true` |
| dryRun    | boolean | Yes      | `true` previews — no file copies or `source_index.json` writes. `false` performs the import.                       | —                        | `true`                                 |

## Expected Output
On `dryRun: true`: returns the planned destination paths, the `source_index.json` entry that would be appended, the `isPrimary` resolution, and `virtualTimelineRequired` if the speaker already has registered sources.

On `dryRun: false`: copies the WAV (and optional CSV) under `audio/original/<speaker>/`, scaffolds `annotations/<speaker>.parse.json` on first import, appends the source to `source_index.json`, and returns `{ ok: true, speaker, destWav, isPrimary, virtualTimelineRequired }`.

## Example Successful Call
First import (dry run):
```json
{
  "speaker": "Khan01",
  "sourceWav": "/external/recordings/Khan01.wav",
  "sourceCsv": "/external/recordings/Khan01.csv",
  "dryRun": true
}
```

Live first import:
```json
{
  "speaker": "Khan01",
  "sourceWav": "/external/recordings/Khan01.wav",
  "sourceCsv": "/external/recordings/Khan01.csv",
  "dryRun": false
}
```

Second source (multi-source speaker):
```json
{
  "speaker": "Khan01",
  "sourceWav": "/external/recordings/Khan01_session2.wav",
  "isPrimary": false,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                            | Symptom                                                                  | Recovery                                                                                                  |
|----------------------------------------------------|--------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Source path outside allowed roots                  | Path-validation error                                                    | Add the directory to `PARSE_EXTERNAL_READ_ROOTS` (`*` to disable the sandbox), or move the source under the project audio dir. |
| Multi-source speaker — virtual timeline not built | `virtualTimelineRequired: true` in response                              | Annotation spanning all sources must be coordinated manually; PARSE doesn't auto-align across WAVs.        |
| Wrong `isPrimary` flag                             | After import, the wrong WAV is treated as primary downstream             | Re-import with explicit `isPrimary: true/false`. Manual fixup may require editing `source_index.json`.     |
| First-import scaffold missing concepts             | `annotations/<speaker>.parse.json` exists but lacks expected concept rows| The scaffold pulls concept IDs from the active project — verify with `project_context_read` that the concept list is populated. |

## Agent Reasoning Notes
This is the typical fresh-onboarding entry point. After it completes, the natural next steps depend on flow:
- For full pipeline annotation: `audio_normalize_start` → `stt_word_level_start` → `forced_align_start` → `ipa_transcribe_acoustic_start`. Or use the workflow macro `run_full_annotation_pipeline`.
- For peaks-only (waveform viewer without compute): `peaks_generate` after the source is registered.

Multi-source speakers are a known PARSE limitation: each WAV registers independently and the virtual timeline must be managed by the user. Don't attempt to derive cross-WAV intervals automatically.

## Related Skills
- `import_processed_speaker` — alternative when annotation alignment already exists.
- `audio_normalize_start`, `stt_word_level_start`, `forced_align_start`, `ipa_transcribe_acoustic_start` — typical post-onboarding chain.
- `run_full_annotation_pipeline` — high-level workflow macro that wraps the chain.
- `peaks_generate` — produce waveform peaks for the viewer.
