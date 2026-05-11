# retranscribe_with_boundaries_start

**Category:** Annotation
**Mutability:** stateful_job (writes `coarse_transcripts/<speaker>.json` with `source=boundary_constrained`)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~240 (short) / ~520 (full)

## One-Sentence Summary
Starts a boundary-constrained STT job: reads the speaker's `tiers.ortho_words` as authoritative segment boundaries, slices the source audio in memory at each window, runs faster-whisper on each slice independently, and merges the results back into `coarse_transcripts/<speaker>.json`.

## When to Use
- When ortho_words boundaries are trusted and you want STT output constrained to those exact windows (no segment-merging surprises from faster-whisper's default boundary inference).
- After `compute_boundaries_start` or `forced_align_start` has produced a clean `tiers.ortho_words` lane and you want to re-derive segment text against those windows.
- For corpora where word-level alignment is more reliable than Whisper's default segmenter and you want STT text aligned to the curated boundaries.

## When NOT to Use
- Without populated `tiers.ortho_words`. The catalog precondition is explicit: ortho_words intervals are required — the slicer has nothing to do without them. Run `compute_boundaries_start` first (or full forced-align).
- For the standard first STT pass — use `stt_start` or `stt_word_level_start` instead. Those work without prior boundaries.
- To write `tiers.ortho_words`. That's what `compute_boundaries_start` does; this tool *reads* it.
- For phoneme-level output — this produces orthographic segments, not IPA. Use `ipa_transcribe_acoustic_start` for IPA.

## Parameters

| Parameter | Type    | Required | Description                                                                                | Default       | Example     |
|-----------|---------|----------|--------------------------------------------------------------------------------------------|---------------|-------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                | —             | `"Khan01"`  |
| language  | string  | No       | ISO 639-1 language code for faster-whisper. Empty/omitted triggers auto-detect. `minLength=0`, `maxLength=8`. | (auto-detect) | `"sdh"`     |
| dryRun    | boolean | No       | If `true`, preview the retranscribe job plan without launching it.                          | `false`       | `true`      |

## Expected Output
On `dryRun: true`: returns the planned slice count (one per `tiers.ortho_words` interval), the speaker's working WAV path, and the resolved language.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, ... }`. **Poll with `retranscribe_with_boundaries_status` until terminal.** On completion the job writes `coarse_transcripts/<speaker>.json` with `source: "boundary_constrained"` so downstream tools can distinguish it from the regular STT cache.

## Example Successful Call
Dry run:
```json
{
  "speaker": "Khan01",
  "language": "ku",
  "dryRun": true
}
```

Live start (auto-detect language):
```json
{
  "speaker": "Khan01"
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                                  |
|------------------------------------------|----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Empty `tiers.ortho_words`                | Job errors immediately                                               | Run `compute_boundaries_start` (or `forced_align_start`) first to populate the BND lane.                  |
| Wrong language detected                  | Garbled per-window STT output                                        | Re-run with explicit `language: "<iso>"`. The cache is overwritten so prior result is discarded.          |
| One bad window contaminates the cache    | One ortho_words interval was wrong → its slice gets garbage STT      | Fix the boundary first (manual edit or rerun `compute_boundaries_start`), then re-run this tool.          |
| `coarse_transcripts` overwritten unexpectedly | Subsequent tools see `source: "boundary_constrained"` not regular STT | This is intentional. If you need a regular sentence-level STT cache, re-run `stt_start` to overwrite.    |

## Agent Reasoning Notes
This is the right tool when you trust the boundaries more than Whisper's segmenter and want STT text aligned to those exact windows. It produces the same `coarse_transcripts/<speaker>.json` shape as `stt_start`, but with `source: "boundary_constrained"` so downstream tools (e.g. cognate compute, IPA windows) know which segmenter produced it. The window-by-window slice is also more robust against long stretches of silence or speaker overlap than full-file Whisper, since each slice is independent.

## Related Skills
- `retranscribe_with_boundaries_status` — poll the returned `jobId`.
- `compute_boundaries_start`, `forced_align_start` — produce `tiers.ortho_words` consumed by this tool.
- `stt_start`, `stt_word_level_start` — alternatives that produce a full-file STT cache (no prior boundaries needed).
