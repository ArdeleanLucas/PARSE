# retranscribe_with_boundaries_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~150 (short) / ~340 (full)

## One-Sentence Summary
Polls the status and progress of a boundary-constrained STT job started by `retranscribe_with_boundaries_start`.

## When to Use
- After every `retranscribe_with_boundaries_start` call, until status reaches `complete` or `error`.
- To resume tracking an in-flight retranscribe job after a session restart (find the `jobId` via `jobs_list_active`).
- To capture the terminal snapshot as audit evidence that `coarse_transcripts/<speaker>.json` was written with `source: "boundary_constrained"`.

## When NOT to Use
- For other class statuses — STT plain has `stt_status`, word-level has `stt_word_level_status`, BND has `compute_boundaries_status`. Use `job_status` for class-agnostic polling.
- For artifact verification — read the cache file back to confirm content; `complete` proves the job ran, not that every slice produced text.

## Parameters

| Parameter | Type   | Required | Description                                       | Default | Example                                  |
|-----------|--------|----------|---------------------------------------------------|---------|------------------------------------------|
| jobId     | string | Yes      | Identifier from `retranscribe_with_boundaries_start`. `minLength=1`, `maxLength=128`. | — | `"550e8400-e29b-41d4-a716-446655440000"` |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, result, ... }`. Terminal states: `complete` (cache written with `source: "boundary_constrained"`) or `error`.

Does not mutate project state.

## Example Successful Call
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Common Failure Modes & How to Recover

| Failure              | Symptom                              | Recovery                                                                            |
|----------------------|--------------------------------------|-------------------------------------------------------------------------------------|
| Unknown jobId        | `status: "not_found"` or tool error  | Find the live `jobId` via `jobs_list_active`.                                       |
| Job stuck `running`  | Progress idle past expected duration | Read `job_logs` — the job logs per-slice progress so you can pinpoint the stalled window. |
| Job ended `error`    | Terminal `error` with message        | `job_logs` carries the failure (often a bad boundary window or audio decode error). |

## Agent Reasoning Notes
This is the matching status tool for `retranscribe_with_boundaries_start`. After completion, audit the `coarse_transcripts/<speaker>.json` file — confirm `source: "boundary_constrained"` and that each segment's window matches the corresponding `tiers.ortho_words` interval. The result here proves the job ran; per-slice quality requires reading the actual cache.

## Related Skills
- `retranscribe_with_boundaries_start` — produces the `jobId` polled here.
- `job_logs`, `job_status` — generic alternatives.
- `annotation_read` — inspect `tiers.ortho_words` and the resulting cache.
