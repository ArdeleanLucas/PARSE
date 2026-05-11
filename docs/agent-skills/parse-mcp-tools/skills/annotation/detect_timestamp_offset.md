# detect_timestamp_offset

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only detection)
**Complexity:** Medium
**Estimated Tokens:** ~280 (short) / ~600 (full)

## One-Sentence Summary
Detects a constant timestamp offset between a speaker's annotation intervals and STT segments for the same audio using monotonic anchor-segment alignment, returning `offsetSec` with confidence and spread so callers can sanity-check before applying.

## When to Use
- When you suspect the speaker's CSV-derived timestamps are uniformly off from the audio (e.g. the recording was edited and shifted, the CSV uses a different time zero).
- Before `apply_timestamp_offset`: this is the auto-detect path that produces the `offsetSec` value.
- When you have an STT job already completed for the speaker and want PARSE to figure out the offset from anchor-word matches instead of feeding manual pairs.

## When NOT to Use
- Without a completed STT job — the tool depends on `sttJobId` to source STT segments. Run `stt_start` or `stt_word_level_start` first.
- When you already have trusted (audio time, csv time) pairs from manual review — use `detect_timestamp_offset_from_pair` instead; it's deterministic and skips the anchor search.
- For non-constant drift. The tool models a single constant offset; if the spread is high (`spreadSec` > ~1s) or `warnings` is non-empty, the audio doesn't have a single-offset relationship to the CSV.
- To apply the offset. This is read-only; pass the returned `offsetSec` into `apply_timestamp_offset` after sanity-checking.

## Parameters

| Parameter          | Type    | Required | Description                                                                                            | Default     | Example          |
|--------------------|---------|----------|--------------------------------------------------------------------------------------------------------|-------------|------------------|
| speaker            | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                            | —           | `"Khan01"`       |
| sttJobId           | string  | No       | Identifier of a completed STT job for the same speaker. `minLength=1`, `maxLength=128`.                | (resolve latest) | `"stt-7f3a"` |
| nAnchors           | integer | No       | Number of annotation anchors to sample. `minimum=2`, `maximum=50`.                                     | (server default) | `12`        |
| bucketSec          | number  | No       | Match window in seconds. `minimum=0.1`, `maximum=30.0`.                                                | (server default) | `1.0`       |
| minMatchScore      | number  | No       | Minimum similarity score for a match to count. `minimum=0.0`, `maximum=1.0`.                            | (server default) | `0.56`      |
| anchorDistribution | string  | No       | `quantile` (default — anchors sampled across timeline) or `earliest` (legacy first-N selection).        | `"quantile"` | `"quantile"`     |

## Expected Output
Returns `{ offsetSec, confidence, nAnchors, totalAnchors, totalSegments, method: "monotonic_alignment", spreadSec, direction, directionLabel, anchorDistribution, reliable, warnings, matches[], annotationPath }`. Treat non-empty `warnings`, low `confidence` (< ~0.7), or high `spreadSec` (> ~1s) as a stop sign — do not pass `offsetSec` to `apply_timestamp_offset` in those cases.

Does not mutate project state.

## Example Successful Call
```json
{
  "speaker": "Khan01",
  "sttJobId": "stt-7f3a",
  "nAnchors": 12,
  "bucketSec": 1.0,
  "minMatchScore": 0.56,
  "anchorDistribution": "quantile"
}
```

Representative high-confidence response:
```json
{
  "readOnly": true,
  "speaker": "Khan01",
  "offsetSec": 2.375,
  "confidence": 0.87,
  "nAnchors": 9,
  "totalAnchors": 12,
  "totalSegments": 184,
  "method": "monotonic_alignment",
  "spreadSec": 0.42,
  "direction": "later",
  "directionLabel": "2.375 s later (toward the end)",
  "reliable": true,
  "warnings": [],
  "matches": [
    {"anchor_index": 0, "anchor_text": "water", "anchor_start": 12.0, "segment_index": 17, "segment_text": "water", "segment_start": 14.375, "score": 0.94, "offset_sec": 2.375}
  ]
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                                      | Recovery                                                                                                  |
|----------------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| Low confidence / few matches           | `confidence < 0.5`, few entries in `matches`                                 | Speaker may not have enough overlap. Try lowering `minMatchScore` cautiously, or switch to `detect_timestamp_offset_from_pair` with manual pairs. |
| High spread                            | `spreadSec > 1s`, `warnings` non-empty                                       | The offset is not constant (drift). Don't apply a global offset — investigate per-region with `detect_timestamp_offset_from_pair` and multiple pairs. |
| Wrong direction                        | `direction` doesn't match expectations                                       | Re-read the `matches[]` array to see which anchor-segment pairs the algorithm chose — false matches show up as outliers. |
| STT job not for this speaker           | Tool errors or matches are garbage                                            | Verify `sttJobId` was for the same speaker. Re-run STT if needed.                                         |
| `anchorDistribution: "earliest"` biased | All anchors concentrated in opening — misses drift later in the recording   | Keep `quantile` (default) unless you specifically need legacy behavior.                                   |

## Agent Reasoning Notes
This is step 1 of the timestamp-correction flow: `detect_timestamp_offset` → inspect for confidence/spread/warnings → `apply_timestamp_offset` (`dryRun: true` first). The monotonic-alignment guarantee means matches must visit anchors and segments in increasing time order — that defeats the false-match-elsewhere-in-recording problem that simpler nearest-neighbor approaches fall into. Don't trust the `offsetSec` blindly: read the matched anchor-segment pairs in the response, confirm they look right, and only then pass it forward. If unsure or if confidence is low, fall back to `detect_timestamp_offset_from_pair` with a couple of trusted manual anchors.

## Related Skills
- `apply_timestamp_offset` — apply the detected offset (always `dryRun: true` first).
- `detect_timestamp_offset_from_pair` — manual-pair alternative when auto-detect is unreliable.
- `stt_start`, `stt_word_level_start` — produce the STT job this tool needs.
- `annotation_read` — inspect the speaker's interval structure before detecting.
