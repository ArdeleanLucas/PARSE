# compute_boundaries_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~160 (short) / ~360 (full)

## One-Sentence Summary
Polls the status and progress of a Boundaries (BND) job started by `compute_boundaries_start`.

## When to Use
- After every `compute_boundaries_start` call, until status reaches `complete` or `error`.
- To pick up an in-flight BND job after a session restart — combine with `jobs_list_active` to find the `jobId`.
- To capture the terminal snapshot as audit evidence that the BND lane was written.

## When NOT to Use
- For other class statuses — each compute class has its own paired `*_status`. Use `job_status` if you don't know the class.
- For artifact-level audit ("did the file actually change?") — read `annotations/<speaker>.parse.json` back through `annotation_read` for ground truth.

## Parameters

| Parameter | Type   | Required | Description                                       | Default | Example                                  |
|-----------|--------|----------|---------------------------------------------------|---------|------------------------------------------|
| jobId     | string | Yes      | Identifier from `compute_boundaries_start`. `minLength=1`, `maxLength=128`. | — | `"550e8400-e29b-41d4-a716-446655440000"` |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, result, ... }`. Terminal states: `complete` (BND lane written) or `error`.

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
| Unknown jobId        | `status: "not_found"` or tool error  | Find a live `jobId` via `jobs_list_active`.                                         |
| Job stuck `running`  | Progress idle past expected duration | Read `job_logs` for the alignment-step logs.                                        |
| Job ended `error`    | Terminal `error` with message        | `job_logs` carries the failure detail.                                              |

## Agent Reasoning Notes
This is the matching status tool for `compute_boundaries_start`. The result payload is structured BND-job inspection data — safe to archive in validation notes, cite as evidence that the job reached terminal state, and compare across polls.

## Related Skills
- `compute_boundaries_start` — produces the `jobId` polled here.
- `annotation_read` — read the BND lane after completion to confirm coverage.
- `job_logs`, `job_status` — generic alternatives for failure diagnosis or unknown classes.
