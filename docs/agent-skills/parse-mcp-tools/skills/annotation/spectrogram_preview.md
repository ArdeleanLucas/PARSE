# spectrogram_preview

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (validation-only placeholder)
**Complexity:** Low
**Estimated Tokens:** ~170 (short) / ~360 (full)

## One-Sentence Summary
A read-only placeholder/backend hook for spectrogram preview requests — validates the requested window bounds and `windowSize` and reports backend capability status, without rendering spectrograms.

## When to Use
- For schema validation only — confirming that bounds (`startSec`, `endSec`) and `windowSize` would be accepted by a future renderer.
- As a capability probe: the response indicates whether the backend currently supports spectrogram rendering.
- In tests and integration checks against the catalog surface.

## When NOT to Use
- To actually obtain a rendered spectrogram. The tool is a placeholder; it does not return PNG/spectral data. There is no current rendering path through MCP.
- For real spectrogram analysis. Render externally (e.g. with librosa or sox) or wait for the backend renderer to land.
- For waveform peaks — that's `peaks_generate`.
- For audio metadata — that's `read_audio_info`.

## Parameters

| Parameter  | Type    | Required | Description                                                                    | Default | Example                                  |
|------------|---------|----------|--------------------------------------------------------------------------------|---------|------------------------------------------|
| sourceWav  | string  | Yes      | Project-audio-relative or allowed absolute WAV path. `minLength=1`, `maxLength=512`. | — | `"audio/working/Khan01/Khan01.wav"` |
| startSec   | number  | Yes      | Window start in seconds. `minimum=0.0`.                                        | —       | `12.0`                                   |
| endSec     | number  | Yes      | Window end in seconds. `minimum=0.0`.                                          | —       | `15.0`                                   |
| windowSize | integer | No       | FFT window size. Enum: `256`, `512`, `1024`, `2048`, `4096`.                   | (server default) | `1024`                            |

## Expected Output
Returns `{ readOnly, sourceWav, startSec, endSec, windowSize, capabilityStatus, message }`. `capabilityStatus` indicates whether spectrogram rendering is currently available; in practice it currently reports a placeholder/unavailable status.

Does not mutate project state.

## Example Successful Call
```json
{
  "sourceWav": "audio/working/Khan01/Khan01.wav",
  "startSec": 12.0,
  "endSec": 15.0,
  "windowSize": 1024
}
```

## Common Failure Modes & How to Recover

| Failure                       | Symptom                                  | Recovery                                                                                            |
|-------------------------------|------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Bounds out of range           | Validation error                         | Verify `endSec > startSec` and both within the WAV duration (see `read_audio_info`).                |
| Invalid `windowSize`          | Validation error                         | Use one of the enum values.                                                                          |
| Treating placeholder as a renderer | Empty / placeholder response | Render externally; the tool is currently a capability probe, not a renderer.                        |

## Agent Reasoning Notes
This is a placeholder/scaffold tool exposed by the catalog. Don't promise users a spectrogram image from it — pass through to external rendering or surface the capability status clearly. The schema is stable enough to wire into UIs that will become real renderers when the backend lands.

## Related Skills
- `read_audio_info` — confirm WAV exists and bounds are sensible.
- `peaks_generate` — actually-produced waveform data (different from spectrogram, but the only existing visualization primitive).
