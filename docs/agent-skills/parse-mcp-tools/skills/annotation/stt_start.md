# stt_start

**Category:** Annotation
**Mutability:** stateful_job (starts a sentence-level STT background job)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~230 (short) / ~500 (full)

## One-Sentence Summary
Starts a bounded sentence-level STT job (faster-whisper) for a project audio file and returns a `jobId` for polling with `stt_status`.

## When to Use
- For sentence-level transcription — segments with start/end times but **no word timestamps**.
- As a first STT pass when word-level precision isn't needed (e.g. for compare-mode anchors, quick coverage check).
- When the audio is already normalized; if not, run `audio_normalize_start` first.

## When NOT to Use
- When you need word-level timestamps for `forced_align_start` or `compute_boundaries_start` — use `stt_word_level_start` instead. Those downstream tools require word seeds, which sentence-level STT doesn't produce.
- For boundary-constrained STT (re-transcribe per ortho_words window) — that's `retranscribe_with_boundaries_start`.
- Without normalized audio. Whisper handles unnormalized audio in principle but PARSE's pipeline assumes the normalized working WAV is the canonical input.

## Parameters

| Parameter | Type    | Required | Description                                                                                | Default       | Example                              |
|-----------|---------|----------|--------------------------------------------------------------------------------------------|---------------|--------------------------------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                | —             | `"Khan01"`                           |
| sourceWav | string  | Yes      | Path to the audio (normalized working WAV usually). `minLength=1`, `maxLength=512`.        | —             | `"audio/working/Khan01/Khan01.wav"` |
| language  | string  | No       | Language hint for faster-whisper. Empty/omitted = auto-detect. `minLength=1`, `maxLength=32`. | (auto-detect) | `"sdh"`                           |
| dryRun    | boolean | No       | If `true`, validate inputs and preview the STT job without launching it.                    | `false`       | `true`                               |

## Expected Output
On `dryRun: true`: returns the resolved source path, model, and language without launching the job.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, sourceWav, language }`. **Poll with `stt_status` until terminal.** On completion the job writes the sentence-level cache to `coarse_transcripts/<speaker>.json`.

## Example Successful Call
Dry run:
```json
{
  "speaker": "Khan01",
  "sourceWav": "audio/working/Khan01/Khan01.wav",
  "language": "ku",
  "dryRun": true
}
```

Live start:
```json
{
  "speaker": "Khan01",
  "sourceWav": "audio/working/Khan01/Khan01.wav"
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                                  |
|----------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Wrong language detected                | Garbled segments                                                     | Re-run with explicit `language: "<iso>"`. Overwriting the cache happens by default — re-running rewrites it.|
| Source WAV missing                     | Job errors quickly                                                   | Verify with `read_audio_info`. Run `audio_normalize_start` if a working WAV isn't present.                |
| Missing word timestamps for downstream | `forced_align_start` errors on lookup                                | Sentence-level STT doesn't produce words. Run `stt_word_level_start` instead before forced-align.         |
| OOM / GPU issues                       | Job ends in `error` with CUDA/torch message                          | Read `job_logs`. faster-whisper has a CPU fallback but is slow.                                           |

## Agent Reasoning Notes
Pick `stt_start` only when you don't need word-level timestamps. For the standard Tier 1 → 2 → 3 pipeline, you almost certainly want `stt_word_level_start` (Tier 1 word-level) instead — it's the same model with `word_timestamps=True`, and downstream forced-align needs the words. Keep this as the cheap-and-fast option for cases that don't care about word boundaries (quick coverage checks, compare-mode anchors).

## Related Skills
- `stt_status` — poll the returned `jobId`.
- `stt_word_level_start` — preferred for word-level output needed by Tier 2.
- `retranscribe_with_boundaries_start` — boundary-constrained alternative.
- `audio_normalize_start`, `read_audio_info` — preflight for the source WAV.
