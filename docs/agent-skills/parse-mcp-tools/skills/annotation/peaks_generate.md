# peaks_generate

**Category:** Annotation
**Mutability:** mutating (writes `peaks/<speaker>.json` or custom `outputPath`)
**Supports Dry Run:** Yes (`dryRun: true` computes peaks without writing)
**Complexity:** Low
**Estimated Tokens:** ~210 (short) / ~460 (full)

## One-Sentence Summary
Generates waveform peak data for a speaker's audio and writes it to `peaks/<speaker>.json` (or a custom `outputPath`) — required for the waveform visualizer after any audio change.

## When to Use
- After `onboard_speaker_import` for a new speaker — the waveform viewer needs peaks before it can render.
- After `audio_normalize_start` completes — the working WAV changed, peaks need to refresh.
- After re-importing a source via `onboard_speaker_import` or `import_processed_speaker` (when `peaksJson` was not supplied).
- For a custom output location (e.g. precomputed peaks to ship with a thesis bundle) via explicit `outputPath`.

## When NOT to Use
- For audio metadata (duration, sample rate, channels) — use `read_audio_info`. Peaks generation is heavier and produces a multi-resolution waveform summary, not metadata.
- Repeatedly on an unchanged audio file. The output is deterministic for a given (audio, `samplesPerPixel`) — re-running rewrites the same content. Only re-run when the underlying audio actually changed.
- With both `speaker` and `audioPath` set ambiguously. `audioPath` overrides `speaker` lookup; if both point at different files, the audio path wins.

## Parameters

| Parameter        | Type    | Required | Description                                                                                       | Default                | Example                              |
|------------------|---------|----------|---------------------------------------------------------------------------------------------------|------------------------|--------------------------------------|
| speaker          | string  | No*      | Speaker ID — resolves audio from annotations. `minLength=1`, `maxLength=200`.                     | —                      | `"Khan01"`                           |
| audioPath        | string  | No*      | Explicit audio path (absolute or project-relative). Overrides `speaker` lookup. `minLength=1`, `maxLength=512`. | — | `"audio/working/Khan01/Khan01.wav"` |
| outputPath       | string  | No       | Where to write peaks JSON. `minLength=1`, `maxLength=512`.                                        | `peaks/<speaker>.json` | `"peaks/Khan01.json"`                |
| samplesPerPixel  | integer | No       | Samples per waveform pixel. `minimum=64`, `maximum=8192`.                                          | `512`                  | `512`                                |
| dryRun           | boolean | No       | If `true`, compute peaks but skip the file write.                                                  | `false`                | `true`                               |

*Provide at least one of `speaker` or `audioPath`.

## Expected Output
On `dryRun: true`: returns the computed peaks payload preview (count of pixels, min/max amplitude per channel) without writing.

On `dryRun: false`: writes the peaks JSON to disk and returns `{ ok: true, outputPath, samplesPerPixel, pixelCount, audioPath }`.

## Example Successful Call
By speaker (default output path):
```json
{
  "speaker": "Khan01"
}
```

Explicit audio + custom output + finer resolution:
```json
{
  "audioPath": "audio/working/Khan01/Khan01.wav",
  "outputPath": "peaks/Khan01_hires.json",
  "samplesPerPixel": 256
}
```

Dry run:
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

## Common Failure Modes & How to Recover

| Failure                              | Symptom                                                            | Recovery                                                                                              |
|--------------------------------------|--------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Neither `speaker` nor `audioPath` set | Tool error                                                         | Pass one. `speaker` is canonical for normal use; `audioPath` for one-off generation.                  |
| Audio not where lookup expects        | Tool error / wrong file                                            | Verify with `read_audio_info`. The speaker lookup resolves audio from annotations metadata.           |
| `samplesPerPixel` too small / too large | Mismatched zoom levels in the viewer                              | Default `512` is a sensible middle ground; lower → more detail, larger file; higher → coarser, faster.|
| Output path outside project           | Validation error                                                   | Project-relative paths only (or absolute paths under allowed read roots).                             |

## Agent Reasoning Notes
Peaks generation is a UI prerequisite, not a pipeline step — without `peaks/<speaker>.json`, the waveform viewer can't render. After any change to the speaker's working WAV (normalize, re-import), this is the right cleanup. Don't run it as a standalone task before the audio is in place — verify with `read_audio_info` first if unsure. The deterministic-output property means you can safely re-run after audio changes without coordination overhead.

## Related Skills
- `read_audio_info` — verify the audio source before generating peaks.
- `audio_normalize_start` — typical predecessor (changes the working WAV).
- `onboard_speaker_import`, `import_processed_speaker` — onboarding flows that may not supply peaks.
