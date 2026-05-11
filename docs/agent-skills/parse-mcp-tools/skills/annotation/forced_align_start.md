# forced_align_start

**Category:** Annotation
**Mutability:** stateful_job (writes Tier 2 alignment artifacts)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium–High
**Estimated Tokens:** ~290 (short) / ~620 (full)

## One-Sentence Summary
Starts a Tier 2 forced-alignment job: runs `torchaudio.functional.forced_align` against `facebook/wav2vec2-xlsr-53-espeak-cv-ft` on each STT word window, producing tight per-word (and optional per-phoneme) boundaries.

## When to Use
- After Tier 1 STT (`stt_word_level_start` ideally; `stt_start` works) — Tier 2 refines word boundaries that Whisper produces only loosely.
- When you need tight word boundaries for downstream IPA transcription (`ipa_transcribe_acoustic_start` reads per-word windows).
- When `emitPhonemes: true` is needed for per-phoneme boundary data alongside per-word.
- For language overrides — `language: "ku"` (default) or another espeak-ng code; this only affects the internal G2P CTC-target builder, not the model's output.

## When NOT to Use
- Without Tier 1 STT output. Forced align consumes the speaker's STT word windows; without them, the job has nothing to align.
- When you only need refined boundaries from cached STT word seeds and don't want the full Tier 2 wav2vec2 pass — `compute_boundaries_start` is the lighter alternative.
- For getting IPA. The internal G2P here is used only to build CTC targets; no G2P output is persisted. For IPA transcription, run `ipa_transcribe_acoustic_start` separately (Tier 3).
- To replace an existing aligned artifact unless explicitly opted in — `overwrite` defaults to `false`. Set `overwrite: true` if you want to discard prior alignment.

## Parameters

| Parameter    | Type    | Required | Description                                                                                | Default | Example         |
|--------------|---------|----------|--------------------------------------------------------------------------------------------|---------|-----------------|
| speaker      | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                | —       | `"Khan01"`      |
| overwrite    | boolean | No       | When `true`, replaces an existing aligned artifact.                                        | `false` | `false`         |
| language     | string  | No       | espeak-ng code for the internal G2P. `minLength=2`, `maxLength=8`.                          | `"ku"`  | `"sdh"`         |
| padMs        | integer | No       | Word-window padding in milliseconds. `minimum=0`, `maximum=500`.                            | (server default) | `100`  |
| emitPhonemes | boolean | No       | If `true`, also emit per-phoneme boundaries alongside per-word.                            | `false` | `true`          |
| dryRun       | boolean | No       | If `true`, preview the alignment job plan without launching the GPU compute.                | `false` | `true`          |

## Expected Output
On `dryRun: true`: returns the resolved working WAV, source STT job/cache, and planned per-word window count.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, ... }`. **Poll with `forced_align_status` until terminal.** On completion the job writes the aligned artifact (tight per-word boundaries, optional phoneme spans) into the speaker's annotation file.

## Example Successful Call
Dry run:
```json
{
  "speaker": "Khan01",
  "language": "ku",
  "padMs": 100,
  "emitPhonemes": false,
  "dryRun": true
}
```

Live start with phoneme output:
```json
{
  "speaker": "Khan01",
  "language": "ku",
  "emitPhonemes": true
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                                  |
|------------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Missing Tier 1 STT                       | Job errors with "no upstream annotation data"                        | Run `stt_word_level_start` first, then re-attempt.                                                        |
| Wrong language → garbage alignment       | Per-word boundaries jitter / drift; CTC targets don't fit            | Re-run with the correct espeak-ng language code. `overwrite: true` to replace the bad result.             |
| OOM / GPU not available                  | Job ends in `error` with CUDA/torch message                          | Read `job_logs`. The wav2vec2 model needs a working GPU; CPU fallback may exist but will be slow.         |
| Existing alignment not replaced          | After live start, prior alignment persists                            | Default `overwrite: false` preserves the artifact. Re-run with `overwrite: true`.                         |
| Wrong word boundary (one bad seed)       | One Tier 1 word window had a bad start — Tier 2 inherits the gap     | Edit the Tier 1 seed via `compute_boundaries_start` or manual review, then re-run forced align.           |

## Agent Reasoning Notes
Tier 2 forced align is the "tight per-word boundary" step in the standard PARSE pipeline (Tier 1 STT → Tier 2 forced align → Tier 3 IPA). For the common case you want this between `stt_word_level_start` and `ipa_transcribe_acoustic_start`. Don't conflate this with `compute_boundaries_start`: that one is cheaper, reuses cached STT word seeds, and writes only the BND lane. This one runs a full wav2vec2 forward pass and writes the Tier 2 alignment artifact. Pair with `pipeline_state_read` to confirm the speaker has Tier 1 STT before starting, and with `forced_align_status` for polling.

## Related Skills
- `forced_align_status` — poll the returned `jobId`.
- `stt_word_level_start` — produces the word seeds Tier 2 aligns.
- `compute_boundaries_start` — lighter alternative for boundary refresh only.
- `ipa_transcribe_acoustic_start` — typical Tier 3 follow-up.
- `pipeline_state_read` — preflight before starting.
