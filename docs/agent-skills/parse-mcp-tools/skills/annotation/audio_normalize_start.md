# audio_normalize_start

**Category:** Annotation
**Mutability:** stateful_job (starts an ffmpeg loudnorm background job)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Low
**Estimated Tokens:** ~210 (short) / ~460 (full)

## One-Sentence Summary
Starts a two-pass ffmpeg loudnorm job for a speaker — converts to mono, 44.1 kHz, -16 LUFS — producing a normalized working WAV at `audio/working/<speaker>/<speaker>.wav`.

## When to Use
- As the first compute step after `onboard_speaker_import` for any new speaker. STT and forced-align both expect the normalized working WAV, not the raw source.
- After re-importing a source WAV (`onboard_speaker_import` with a refreshed file) — re-normalize before downstream tiers will see the new audio.
- When `pipeline_state_read` reports `normalize.done: false` and the source audio is present.

## When NOT to Use
- Repeatedly on the same already-normalized speaker. ffmpeg loudnorm is idempotent in result but the job will still rewrite the working WAV and may invalidate downstream caches if not coordinated.
- For source-file edits, format conversion, or sample-rate changes beyond loudnorm. The tool is a two-pass loudness normalizer, not a general audio editor.
- When the source isn't where the tool expects. If `sourceWav` is omitted, the tool resolves the speaker's primary source from `source_index.json`; a missing/wrong primary causes confusing failures. Verify with `read_audio_info` first if unsure.

## Parameters

| Parameter | Type    | Required | Description                                                                                  | Default                  | Example                            |
|-----------|---------|----------|----------------------------------------------------------------------------------------------|--------------------------|------------------------------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                  | —                        | `"Khan01"`                         |
| sourceWav | string  | No       | Project-relative or absolute path to source WAV. Must be inside `PARSE_EXTERNAL_READ_ROOTS` if absolute. | speaker's primary source | `"audio/original/Khan01/raw.wav"` |
| dryRun    | boolean | No       | If `true`, preview the normalize job without launching ffmpeg.                               | `false`                  | `true`                             |

## Expected Output
On `dryRun: true`: returns the resolved source path, planned output path, and ffmpeg command preview without launching anything.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, sourceWav, ... }`. **Poll with `audio_normalize_status` until terminal.** On completion the job writes `audio/working/<speaker>/<speaker>.wav` and updates the working-audio entry in project metadata.

## Example Successful Call
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

Live start:
```json
{
  "speaker": "Khan01"
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                       | Recovery                                                                                                  |
|------------------------------------------|---------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Source WAV missing                       | Job errors quickly with "no source audio"                     | Verify with `read_audio_info` against the expected path. Re-import via `onboard_speaker_import` if needed.|
| Source outside allowed roots             | Path-validation error                                         | Move the source under the project audio dir, or add the parent to `PARSE_EXTERNAL_READ_ROOTS`.            |
| ffmpeg failure (corrupt source)          | Job reaches `status: "error"`                                 | Read `job_logs` on the `jobId` for the ffmpeg stderr. Re-encode the source externally and re-import.      |
| Downstream caches stale after re-norm    | STT or forced-align job ran against the old working WAV       | Re-normalize first, then re-run STT (`stt_word_level_start` with `overwrite`-equivalent intent).          |

## Agent Reasoning Notes
Normalize is the foundation of every downstream pipeline step. If `pipeline_state_read` says `normalize.can_run: true` and `done: false`, this is the next action. After it completes, all downstream tiers should treat their inputs as invalidated and be re-run if they were computed against an older working WAV. Pair with `read_audio_info` for pre-flight ("is the source actually there?") and `audio_normalize_status` for polling.

## Related Skills
- `audio_normalize_status` — poll the returned `jobId`.
- `read_audio_info` — verify source path/metadata before starting.
- `onboard_speaker_import` — typical predecessor for fresh-speaker flows.
- `pipeline_state_read` — confirms `normalize.can_run` and whether downstream tiers exist.
