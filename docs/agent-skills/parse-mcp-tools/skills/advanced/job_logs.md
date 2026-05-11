# job_logs

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only log retrieval)
**Complexity:** Low
**Estimated Tokens:** ~210 (short) / ~470 (full)

## One-Sentence Summary
Reads timestamped structured log entries for any PARSE background job by `jobId`, with offset/limit paging for long histories.

## When to Use
- Diagnosing a job that ended in `status: "error"` — the snapshot only carries one error string, but `job_logs` shows the path that led to it.
- Following a long job mid-run when you want more detail than the periodic `progress` updates from `compute_status` or `job_status`.
- Paging through very long log histories (forced-align on a multi-hour speaker can produce hundreds of entries).
- Auditing what a job actually did after the fact (which steps ran, when each progress checkpoint fired, what messages the worker emitted).

## When NOT to Use
- For the current job status — use `job_status` (any class) or `compute_status` (compute-class only). They return the snapshot directly with the latest `progress` and `message`.
- To audit project artifacts a job wrote. Logs describe *what the worker did*; for the actual file contents, read `annotations/<speaker>.parse.json` or the relevant artifact back through the appropriate read tool.
- For locating a `jobId` you don't know — `jobs_list` and `jobs_list_active` are the discovery tools.

## Parameters

| Parameter | Type    | Required | Description                                                                | Default | Example                                  |
|-----------|---------|----------|----------------------------------------------------------------------------|---------|------------------------------------------|
| jobId     | string  | Yes      | Job identifier from any `*_start` tool. `minLength=1`, `maxLength=128`.    | —       | `"550e8400-e29b-41d4-a716-446655440000"` |
| offset    | integer | No       | Starting index for paging. `minimum=0`, `maximum=10000`.                   | `0`     | `100`                                    |
| limit     | integer | No       | Maximum number of entries to return. `minimum=1`, `maximum=200`.           | (server default) | `50`                              |

## Expected Output
Returns `{ jobId, logs, count, offset, limit, logCount }`. Each entry in `logs` carries `ts` (ISO 8601), `level` (`info`/`warn`/`error`/`debug`), `event` (`job.created`, `job.progress`, `job.complete`, `job.error`, …), `message`, `source`, and optionally `progress`. Use `count` (total entries currently retained) to know when you've paged to the end.

Does not mutate project state.

## Example Successful Call
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "offset": 0,
  "limit": 50
}
```

Representative response:
```json
{
  "readOnly": true,
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "count": 3,
  "offset": 0,
  "limit": 50,
  "logs": [
    {"ts": "2026-05-10T20:15:00Z", "level": "info", "event": "job.created",  "message": "Job created",                "progress": 0.0},
    {"ts": "2026-05-10T20:15:08Z", "level": "info", "event": "job.progress", "message": "Aligning Tier 1 word windows", "progress": 42.0}
  ],
  "logCount": 2
}
```

## Common Failure Modes & How to Recover

| Failure                  | Symptom                                       | Recovery                                                                                                       |
|--------------------------|-----------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| Unknown jobId            | Tool error / empty `logs`                     | The job may have expired from the in-memory registry. Use `jobs_list` to find currently-tracked jobs.          |
| Logs paged out / retention truncation | `count` matches the page but `logs` for older offsets are gone | The registry retains a bounded log history per job. Capture the tail you need at job completion, don't rely on retrieval days later. |
| Page step too large      | Validation error (`limit > 200`)              | Cap `limit` at 200; iterate with `offset += limit` until `offset + len(logs) >= count`.                        |

## Agent Reasoning Notes
Reach for `job_logs` only after `compute_status` / `job_status` shows something interesting — an `error`, a stalled `progress`, or a `complete` status with unexpected counts. The status snapshot is cheaper than reading every log entry, so use logs as a second-level diagnostic, not a primary one. When paging long logs, treat `count` as the source of truth for "is there more" rather than relying on whether the returned `logs` array is shorter than `limit`.

## Related Skills
- `job_status`, `compute_status` — primary status polls; consult logs only when these surface something unexpected.
- `jobs_list`, `jobs_list_active` — find a `jobId` when you don't have one.
