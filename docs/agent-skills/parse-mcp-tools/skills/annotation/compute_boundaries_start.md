# compute_boundaries_start

**Category:** Annotation
**Mutability:** stateful_job (writes `tiers.ortho_words` on completion)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~250 (short) / ~530 (full)

## One-Sentence Summary
Starts a standalone Boundaries (BND) job: Tier 2 forced alignment over cached STT word timestamps, writing refined per-word boundaries to `tiers.ortho_words` — without rerunning Whisper or IPA.

## When to Use
- When STT word-level output exists (`coarse_transcripts/<speaker>.json` with word timestamps) and the user wants tight word boundaries without paying the cost of a full forced-align rerun.
- After editing the cached STT word seeds and wanting to re-derive boundaries from them.
- As a faster, cheaper alternative to `forced_align_start` when you only need the BND lane refreshed and not full Tier 2 wav2vec2 alignment.

## When NOT to Use
- Without cached STT word timestamps. The catalog precondition is explicit: `coarse_transcripts/<speaker>.json` must contain segment-level word timestamps. Run `stt_word_level_start` first if absent.
- For full forced-alignment with phoneme-level boundaries — use `forced_align_start` (richer, slower, optional `emitPhonemes`).
- For boundary-constrained STT (re-transcribe each ortho_words window) — that's `retranscribe_with_boundaries_start`; it reads `tiers.ortho_words`, this tool writes it.
- When you want to preserve manually-adjusted intervals. `overwrite: true` discards them; default `overwrite: false` keeps them and only fills gaps.

## Parameters

| Parameter | Type    | Required | Description                                                                                  | Default | Example     |
|-----------|---------|----------|----------------------------------------------------------------------------------------------|---------|-------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                  | —       | `"Khan01"`  |
| overwrite | boolean | No       | If `true`, discards `manuallyAdjusted` ortho_words intervals and rebuilds the lane fully.    | `false` | `false`     |
| dryRun    | boolean | No       | If `true`, preview the BND job plan without launching it.                                    | `false` | `true`      |

## Expected Output
On `dryRun: true`: returns the plan — speaker, source cache file, number of word seeds, planned BND lane writes.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, ... }`. **Poll with `compute_boundaries_status` until terminal.** On completion the job writes refined intervals into `annotations/<speaker>.parse.json` under `tiers.ortho_words`.

## Example Successful Call
Dry run:
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

Live start (preserve manually-adjusted intervals):
```json
{
  "speaker": "Khan01"
}
```

Full rebuild (loses manual edits):
```json
{
  "speaker": "Khan01",
  "overwrite": true
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                                  |
|------------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Missing word-level STT cache             | Job errors immediately with "no word timestamps"                     | Run `stt_word_level_start` first to populate `coarse_transcripts/<speaker>.json`.                         |
| `overwrite: true` loses manual edits     | After completion, `manuallyAdjusted` intervals are gone               | No auto-rollback. Snapshot `annotations/<speaker>.parse.json` before any `overwrite: true` BND run.       |
| BND lane partial after success           | `pipeline_state_read` shows `ortho_words.full_coverage: false`       | The cached STT word output didn't cover the whole recording. Re-run `stt_word_level_start` full-file first.|

## Agent Reasoning Notes
This is the lightweight boundary refresh path — use it when you have STT word seeds and want tight boundaries cheaply. For deeper alignment with optional phoneme boundaries, `forced_align_start` is the heavier alternative. Pair with `retranscribe_with_boundaries_start` after this completes if you also want to re-transcribe each window with bounded faster-whisper slices. Always check `pipeline_state_read.ortho_words.full_coverage` after the job — `done: true` alone doesn't prove the whole recording was covered.

## Related Skills
- `compute_boundaries_status` — poll the returned `jobId`.
- `stt_word_level_start` — produces the word timestamps this tool consumes.
- `forced_align_start` — heavier alternative with phoneme-level output.
- `retranscribe_with_boundaries_start` — downstream tool that reads `tiers.ortho_words`.
