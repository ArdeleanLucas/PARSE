# stt_word_level_start

**Category:** Annotation
**Mutability:** stateful_job (starts a word-level STT background job)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~250 (short) / ~540 (full)

## One-Sentence Summary
Starts a word-level (Tier 1 acoustic alignment) STT job — faster-whisper with `word_timestamps=True`, producing segments with nested `words[]` arrays of `(word, start, end, prob)` spans.

## When to Use
- As the canonical Tier 1 step for the standard PARSE pipeline (Tier 1 STT → Tier 2 forced align → Tier 3 IPA).
- Whenever a downstream tool needs word seeds — `forced_align_start`, `compute_boundaries_start`.
- For corpora where you'll need word-level timestamps for any subsequent operation (timestamp offset detection anchors, cross-speaker alignment, etc.).

## When NOT to Use
- For sentence-level segments only (no words needed) — `stt_start` is the cheaper sibling.
- For boundary-constrained STT (per-window slices) — that's `retranscribe_with_boundaries_start`.
- Without normalized audio. Run `audio_normalize_start` first if the working WAV doesn't exist.

## Parameters

| Parameter | Type    | Required | Description                                                                                | Default       | Example                              |
|-----------|---------|----------|--------------------------------------------------------------------------------------------|---------------|--------------------------------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                | —             | `"Khan01"`                           |
| sourceWav | string  | Yes      | Path to the audio (normalized working WAV usually). `minLength=1`, `maxLength=512`.        | —             | `"audio/working/Khan01/Khan01.wav"` |
| language  | string  | No       | Language hint for faster-whisper. Empty/omitted = auto-detect. `minLength=1`, `maxLength=32`. | (auto-detect) | `"sdh"`                           |
| dryRun    | boolean | No       | If `true`, validate inputs and preview the job without launching it.                       | `false`       | `true`                               |

## Expected Output
On `dryRun: true`: returns the resolved source path, model, and language without launching the job.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, sourceWav, language }`. **Poll with `stt_word_level_status` until terminal.** On completion the job writes `coarse_transcripts/<speaker>.json` with segments containing nested `words[]` payloads. Long full-file runs chunk automatically; terminal job `result` can include `chunks[]`, `duration_sec`, and `device`, while the cache remains a flat merged `segments[]` list.

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
| Wrong language detected                | Garbled segments / nonsense words                                    | Re-run with explicit `language: "<iso>"`. The cache is overwritten by re-running.                         |
| Source WAV missing                     | Job errors quickly                                                   | Verify with `read_audio_info`. Run `audio_normalize_start` first.                                         |
| Word timestamps low quality            | `words[].prob` is low across the board                               | Audio quality issue — re-normalize or improve the source. Tier 2 forced-align will refine the boundaries even if Tier 1 is loose. |
| OOM / GPU issues                       | Job ends in `error` with CUDA/torch message                          | Read `job_logs`. faster-whisper falls back to CPU but slowly.                                             |

## Agent Reasoning Notes
For long recordings, keep the default 10-minute STT chunks unless a specific failure requires smaller chunks; do not disable chunking for ordinary fieldwork. Inspect terminal `result.chunks[]` and `job_logs` before rerunning blindly.

This is the canonical Tier 1 step. The name is intentionally explicit ("word_level") so agents can distinguish it from plain sentence-level STT. After completion, the standard chain is `forced_align_start` (Tier 2, tight per-word boundaries) → `ipa_transcribe_acoustic_start` (Tier 3, IPA). For users who don't want to run the full chain, `compute_boundaries_start` is a faster path that consumes these word seeds without re-running wav2vec2.

## Related Skills
- `stt_word_level_status` — poll the returned `jobId`.
- `stt_start` — sentence-level alternative (no word timestamps).
- `forced_align_start`, `compute_boundaries_start` — typical Tier 2 follow-ups.
- `detect_timestamp_offset` — consumes the resulting STT segments for offset detection.
- `audio_normalize_start`, `read_audio_info` — preflight for the source WAV.
