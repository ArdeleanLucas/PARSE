# apply_timestamp_offset

**Category:** Annotation
**Mutability:** mutating (writes `annotations/<speaker>.parse.json`)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Low–Medium
**Estimated Tokens:** ~210 (short) / ~470 (full)

## One-Sentence Summary
Shifts every annotation interval (start and end) for one speaker by a constant `offsetSec`, rewriting `annotations/<speaker>.parse.json` — the standard fix when CSV-derived timestamps are uniformly offset from the audio.

## When to Use
- After `detect_timestamp_offset` or `detect_timestamp_offset_from_pair` returns a high-confidence offset and you've sanity-checked the matched anchors.
- When you have one or more trusted (audio time, csv/annotation time) pairs and want to apply the resulting `offsetSec` to the whole speaker.
- For a "the recording was edited and shifted by X seconds" cleanup — the offset is constant across the file.

## When NOT to Use
- When the offset is *not* constant (the CSV drifts non-linearly relative to audio) — this tool applies one shift to every interval. Drift requires per-interval re-alignment, not a global offset.
- Without a dry-run preview first. `dryRun` is required in the schema for a reason: the file is rewritten in place and a wrong sign value can scramble all intervals across the recording.
- For boundary-level refinement — use `forced_align_start` or `compute_boundaries_start` for tight per-word boundaries, not a global shift.

## Parameters

| Parameter | Type    | Required | Description                                                                                  | Default | Example     |
|-----------|---------|----------|----------------------------------------------------------------------------------------------|---------|-------------|
| speaker   | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                  | —       | `"Khan01"`  |
| offsetSec | number  | Yes      | Seconds to add to every interval start/end. Negative values pull timestamps earlier.         | —       | `2.375`     |
| dryRun    | boolean | Yes      | `true` previews; `false` writes. Always run with `true` first.                               | —       | `true`      |

## Expected Output
On `dryRun: true`: returns the preview — number of intervals that would shift, the new min/max start/end times, and any out-of-range warnings. No file write.

On `dryRun: false`: rewrites `annotations/<speaker>.parse.json` in place with every interval's `start_sec` and `end_sec` incremented by `offsetSec`. Returns `{ ok: true, speaker, offsetSec, intervalsShifted, annotationPath }`. The previous file content is not automatically backed up — callers that need rollback must snapshot first.

## Example Successful Call
Dry run (mandatory first step):
```json
{
  "speaker": "Khan01",
  "offsetSec": 2.375,
  "dryRun": true
}
```

Live apply (only after confirming the dry-run looks right):
```json
{
  "speaker": "Khan01",
  "offsetSec": 2.375,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                                | Recovery                                                                                              |
|----------------------------------------|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Wrong sign on offset                   | All intervals shift the wrong direction; some go negative              | Re-read the original file (no auto-backup). If unrecoverable, re-import from source CSV via `onboard_speaker_import` and re-derive. |
| Offset pushes intervals past EOF       | Some intervals have `end_sec > duration_sec`                           | Cap the offset or trim the affected intervals. Re-run `detect_timestamp_offset` to confirm the value. |
| Drift mistaken for offset              | After apply, some regions of the audio align but others don't          | The offset is not constant. Don't keep stacking offsets — restore from source and run per-region alignment via `forced_align_start`. |
| Missing annotation file                | Tool error                                                             | Speaker must have an existing annotation file. Import via `onboard_speaker_import` first.             |

## Agent Reasoning Notes
This tool is the apply step in a three-step flow: (1) detect the offset (`detect_timestamp_offset` for auto or `detect_timestamp_offset_from_pair` for manual), (2) inspect the result for high confidence + low spread + no warnings, (3) apply here with `dryRun: true` first, then `false`. Never skip the dry-run; the file is rewritten in place without an auto-backup. Treat the `offsetSec` value as load-bearing data — confirm sign and magnitude before applying, especially when the detected `direction` is `"earlier"` (negative offset).

## Related Skills
- `detect_timestamp_offset` — auto-detect from STT anchors.
- `detect_timestamp_offset_from_pair` — manual offset from trusted pairs.
- `annotation_read` — audit the file before and after.
- `forced_align_start`, `compute_boundaries_start` — alternative for per-word boundary correction (not global shift).
