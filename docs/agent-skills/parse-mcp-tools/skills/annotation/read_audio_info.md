# read_audio_info

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (metadata read)
**Complexity:** Low
**Estimated Tokens:** ~150 (short) / ~340 (full)

## One-Sentence Summary
Reads metadata for a WAV file under the project audio directory: duration, sample rate, channels, sample width, frame count, and file size — without returning audio samples.

## When to Use
- Pre-flight check before `audio_normalize_start`, `stt_start`, or any tool that consumes a WAV — confirm the file exists, is readable, and has plausible duration/sample rate.
- Diagnosing pipeline-state mismatches — "the WAV is 6 minutes but only 30s of intervals?" → `read_audio_info` confirms the WAV duration.
- Verifying a normalize job actually produced a 44.1 kHz / mono output by re-reading the working WAV.
- Choosing `samplesPerPixel` for `peaks_generate` — duration plus sample rate determine total samples.

## When NOT to Use
- To read audio samples. This is metadata only; no PCM data is returned.
- For peaks data — that's `peaks_generate`.
- For external files outside `PARSE_EXTERNAL_READ_ROOTS`. The path must be project-audio-relative or an allowed absolute path.

## Parameters

| Parameter | Type   | Required | Description                                                                                                | Default | Example                                  |
|-----------|--------|----------|------------------------------------------------------------------------------------------------------------|---------|------------------------------------------|
| sourceWav | string | Yes      | Project-audio-relative WAV path (e.g. `audio/working/Khan01/Khan01.wav`) or an allowed absolute path. `minLength=1`, `maxLength=512`. | — | `"audio/working/Khan01/Khan01.wav"` |

## Expected Output
Returns `{ sourceWav, durationSec, sampleRate, channels, sampleWidth, frameCount, fileSizeBytes }`. Does not return audio samples.

Does not mutate project state.

## Example Successful Call
```json
{
  "sourceWav": "audio/working/Khan01/Khan01.wav"
}
```

## Common Failure Modes & How to Recover

| Failure                       | Symptom                                | Recovery                                                                                            |
|-------------------------------|----------------------------------------|-----------------------------------------------------------------------------------------------------|
| File not found                | Tool error                             | Verify the path. If a speaker has multiple sources, check `source_index.json` or `speakers_list`.   |
| Outside allowed roots         | Path-validation error                   | Use a project-relative path, or add the parent directory to `PARSE_EXTERNAL_READ_ROOTS`.            |
| Unexpected sample rate / channels | Returned values don't match expectations | The source may not be normalized — run `audio_normalize_start` to get mono / 44.1 kHz / -16 LUFS.   |
| Corrupt WAV                   | Tool error reading header              | The file may be truncated. Re-import via `onboard_speaker_import` from a known-good source.         |

## Agent Reasoning Notes
This is the cheap "does the audio file look right?" check. Run it before any compute-heavy tool to fail fast if the source is missing/corrupt. Pair with `pipeline_state_read` — the latter reports per-tier `done` / `full_coverage`, this reports the underlying file properties. The two together answer "is the source there?" and "did the pipeline process it?" separately.

## Related Skills
- `audio_normalize_start` — typical follow-up if the source isn't normalized.
- `peaks_generate` — needs the same audio path.
- `pipeline_state_read` — coverage view across pipeline tiers.
