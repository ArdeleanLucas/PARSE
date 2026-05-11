# detect_timestamp_offset_from_pair

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only computation)
**Complexity:** Low–Medium
**Estimated Tokens:** ~240 (short) / ~520 (full)

## One-Sentence Summary
Computes a constant timestamp offset from one or more trusted (CSV/annotation time, audio time) pairs — deterministic, no STT, no statistical anchor search — returning the same response shape as `detect_timestamp_offset` so the result can be piped straight into `apply_timestamp_offset`.

## When to Use
- When you (or the user) already know exactly where one or more lexemes are in the audio. Skip the anchor search entirely.
- When `detect_timestamp_offset` returns low confidence or has too few matches to be trusted.
- For high-confidence shifts where one good manual anchor is worth a dozen auto-detected ones.
- With multiple pairs across the timeline to detect drift — pass 3+ pairs; the response surfaces MAD-style spread and per-pair warnings when pairs disagree by more than ~2 s.

## When NOT to Use
- When you don't have a single trusted (audio time, csv/concept time) pair — there's nothing to compute from. Use `detect_timestamp_offset` for the anchor-search auto-detect path.
- For non-constant drift across the whole recording. Multiple pairs reveal drift (large MAD spread), but the tool still returns a median offset. Drift is a real problem that no single global offset can fix.
- For STT-based segment matching. The catalog description is explicit: "no STT, no statistics-on-text, no false matches". Mixing STT segments into the pairs is the wrong tool — use `detect_timestamp_offset` for that.

## Parameters

Two argument shapes are accepted:

**Single pair**

| Parameter    | Type    | Required | Description                                                                          | Example      |
|--------------|---------|----------|--------------------------------------------------------------------------------------|--------------|
| speaker      | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                          | `"Khan01"`   |
| audioTimeSec | number  | Yes      | The time in the audio where the lexeme actually occurs. `minimum=0.0`.               | `14.375`     |
| csvTimeSec   | number  | One of csvTimeSec/conceptId required | CSV-side timestamp for the same lexeme.                          | `12.0`       |
| conceptId    | string  | One of csvTimeSec/conceptId required | Concept ID — the tool resolves the annotation-side timestamp.   | `"42"`       |

**Multiple pairs**

| Parameter | Type    | Required | Description                                                                                                      | Example                                          |
|-----------|---------|----------|------------------------------------------------------------------------------------------------------------------|--------------------------------------------------|
| speaker   | string  | Yes      | Speaker ID.                                                                                                      | `"Khan01"`                                       |
| pairs     | object[] | Yes     | Array of pair objects. Each entry needs `audioTimeSec` + (`csvTimeSec` or `conceptId`). 2+ pairs → median offset, MAD spread, drift warnings. | `[{"csvTimeSec": 12.0, "audioTimeSec": 14.375}, ...]` |

## Expected Output
Same shape as `detect_timestamp_offset`: `{ offsetSec, confidence, spreadSec, direction, warnings, matches[], annotationPath, ... }`. With 2+ pairs, `spreadSec` carries the MAD across per-pair offsets and `warnings` flags any pair that disagrees with the median by more than ~2 s.

Does not mutate project state.

## Example Successful Call
Single trusted pair with CSV time:
```json
{
  "speaker": "Khan01",
  "csvTimeSec": 12.0,
  "audioTimeSec": 14.375
}
```

Single pair via concept ID (tool resolves the CSV side):
```json
{
  "speaker": "Khan01",
  "conceptId": "42",
  "audioTimeSec": 14.375
}
```

Multiple pairs (drift check):
```json
{
  "speaker": "Khan01",
  "pairs": [
    {"csvTimeSec": 12.0, "audioTimeSec": 14.375},
    {"csvTimeSec": 48.5, "audioTimeSec": 50.875},
    {"conceptId": "108", "audioTimeSec": 91.25}
  ]
}
```

## Common Failure Modes & How to Recover

| Failure                                              | Symptom                                                                    | Recovery                                                                                                              |
|------------------------------------------------------|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Pair mixes shape variants                            | Validation error — neither single-pair nor `pairs` array satisfied         | Pick one form. For multiple anchors, use `pairs`. For one anchor, use `audioTimeSec` + (`csvTimeSec` OR `conceptId`). |
| Unknown `conceptId`                                  | Tool error or empty result                                                 | Verify concept ID via `project_context_read` (`concepts` section) or `list_concepts_by_tag`.                          |
| Drift detected (multiple pairs disagree)             | High `spreadSec`, non-empty `warnings`                                     | Don't apply a global offset. Investigate per-region — there may be multiple offsets across the recording.             |
| Wrong sign                                           | `offsetSec` would push intervals before t=0 when applied                   | Re-read your pair. The convention is `audioTimeSec - csvTimeSec` = offset; if applying pulls intervals negative, the pair is inverted. |

## Agent Reasoning Notes
Reach for this when auto-detect is unreliable or when the user has reviewed the audio and knows exactly where a lexeme starts. Two pairs from opposite ends of the recording is a cheap drift check — if they agree within MAD, a global offset is safe; if they disagree, drift is real and a single shift won't fix the file. The output is drop-in compatible with `apply_timestamp_offset` — same `offsetSec` field, same convention.

## Related Skills
- `apply_timestamp_offset` — apply the computed offset (always `dryRun: true` first).
- `detect_timestamp_offset` — auto-detect alternative when no manual pairs are available.
- `annotation_read` — inspect the file before/after.
- `project_context_read` — verify `conceptId` values.
