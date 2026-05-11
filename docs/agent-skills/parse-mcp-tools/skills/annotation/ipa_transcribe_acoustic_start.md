# ipa_transcribe_acoustic_start

**Category:** Annotation
**Mutability:** stateful_job (writes the speaker's IPA tier)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium–High
**Estimated Tokens:** ~240 (short) / ~530 (full)

## One-Sentence Summary
Starts a Tier 3 acoustic IPA job: runs `facebook/wav2vec2-xlsr-53-espeak-cv-ft` CTC on each ortho interval's audio window and writes the decoded phoneme string into the speaker's IPA tier.

## When to Use
- After Tier 2 forced alignment has populated tight per-word boundaries (`forced_align_start` → `compute_boundaries_start` → or both).
- For the standard PARSE Tier 1 → Tier 2 → Tier 3 chain — this is the IPA step.
- When `pipeline_state_read.ipa.can_run: true` for the speaker.
- For the UI "Actions → Run IPA transcription" equivalent — same backend.

## When NOT to Use
- Without populated ortho intervals. The catalog precondition is explicit: ortho data is the upstream input. Run forced-align (Tier 2) or `compute_boundaries_start` first.
- Expecting non-wav2vec2 IPA. The catalog description states: "wav2vec2 is the ONLY IPA engine — there are no text-based fallbacks". Don't pass `language: "ku"` expecting espeak-style G2P; this is an acoustic model only.
- For phoneme-level boundaries. Use `forced_align_start` with `emitPhonemes: true` for boundaries; this tool produces phoneme *strings* per ortho interval, not phoneme spans.
- To replace existing IPA cells unless `overwrite: true`. Default is non-destructive: only empty IPA cells get filled.

## Parameters

| Parameter | Type    | Required | Description                                                                  | Default | Example     |
|-----------|---------|----------|------------------------------------------------------------------------------|---------|-------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                  | —       | `"Khan01"`  |
| overwrite | boolean | No       | When `true`, replaces existing non-empty IPA cells.                          | `false` | `false`     |
| dryRun    | boolean | No       | If `true`, preview the IPA job plan without launching it.                    | `false` | `true`      |

## Expected Output
On `dryRun: true`: returns the planned per-interval wav2vec2 windows count and the speaker's working WAV path.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, ... }`. **Poll with `ipa_transcribe_acoustic_status` until terminal.** On completion, each ortho interval has its IPA cell populated with the model's CTC decode.

## Example Successful Call
Dry run:
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

Live start (non-destructive):
```json
{
  "speaker": "Khan01"
}
```

Replace existing IPA cells:
```json
{
  "speaker": "Khan01",
  "overwrite": true
}
```

## Common Failure Modes & How to Recover

| Failure                                 | Symptom                                                              | Recovery                                                                                                  |
|-----------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Missing ortho intervals                 | Job errors with "no upstream annotation data"                        | Run `forced_align_start` or `compute_boundaries_start` first.                                             |
| Existing IPA cells untouched            | Live run completes but some cells are unchanged                      | Default `overwrite: false`. Re-run with `overwrite: true` to replace existing content.                    |
| OOM / GPU issues                        | Job ends in `error` with CUDA/torch message                          | Read `job_logs`. Wav2vec2 CTC needs GPU memory; CPU fallback is slow if it works at all.                  |
| Garbage IPA output                      | Phoneme strings look implausible                                     | The ortho boundary that produced this window is wrong — review with `annotation_read` and re-align via `forced_align_start`. |

## Agent Reasoning Notes
This is the IPA step of the Tier 1 → Tier 2 → Tier 3 pipeline. Don't run it before forced-align: the IPA decode is per-ortho-interval, and bad boundaries produce bad IPA. Always confirm `pipeline_state_read.ortho.full_coverage: true` before kicking off IPA. The `overwrite: false` default is the safer choice; only flip to `true` when the user has explicitly confirmed they want to replace existing IPA data (which may have been manually corrected).

## Related Skills
- `ipa_transcribe_acoustic_status` — poll the returned `jobId`.
- `forced_align_start`, `compute_boundaries_start` — populate ortho intervals before this runs.
- `pipeline_state_read` — confirm `ipa.can_run` before starting.
- `annotation_read` — verify the IPA cells after completion.
