# job_status

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~200 (short) / ~460 (full)

## One-Sentence Summary
Reads the generic status snapshot of any PARSE background job by `jobId` — class-agnostic, works across STT, normalize, compute, onboard, forced-align, IPA, retranscribe, and any other job type.

## When to Use
- When you don't know (or don't want to assume) the job class — `job_status` accepts any `jobId` and returns a uniform shape.
- As the single status interface in code paths that orchestrate multiple kinds of jobs (e.g. a chat agent loop that may have started STT or IPA or normalize).
- To inspect `meta` (speaker, language, computeType) and `locks` (active resources, TTL) for a job whose context you've lost.
- After a session restart when you have a `jobId` from `jobs_list_active` but don't remember which class started it.

## When NOT to Use
- For compute-class jobs (`pipeline_run`, `run_full_annotation_pipeline`, ortho/ipa/contact-lexeme starters) when you want the rich per-step `result.results.<step>` and `result.summary` payload — use `compute_status` instead.
- For class-specific richer fields some `*_status` tools expose (e.g. STT `segmentsProcessed`/`totalSegments`). The matching `*_status` tool returns the same plus class-specific extras.
- For diagnosis after an error — read `job_logs` for line-level detail; `job_status.error` is one string.

## Parameters

| Parameter | Type   | Required | Description                                                       | Default | Example                                  |
|-----------|--------|----------|-------------------------------------------------------------------|---------|------------------------------------------|
| jobId     | string | Yes      | Job identifier. `minLength=1`, `maxLength=128`.                   | —       | `"550e8400-e29b-41d4-a716-446655440000"` |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, errorCode, result, createdAt, updatedAt, completedAt, meta, locks, logCount }`. Key fields:

- `status` — one of `queued`, `running`, `complete`, `error`, `not_found`. Treat `complete` and `error` as terminal; `not_found` means the job has expired or was never created.
- `type` — class identifier like `compute:forced_align`, `stt`, `onboard:speaker_import`.
- `result` — `null` until `status == "complete"`; shape varies by job class.
- `meta` — class-specific context (`speaker`, `language`, `computeType`).
- `locks` — held resources with TTL; useful to detect "this speaker is busy" before kicking off another job for the same target.

Does not mutate project state.

## Example Successful Call
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000"
}
```

Representative running response:
```json
{
  "readOnly": true,
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "type": "compute:forced_align",
  "status": "running",
  "progress": 42.0,
  "message": "Aligning Tier 1 word windows",
  "error": null,
  "result": null,
  "meta": {"speaker": "Fail02", "computeType": "forced_align"},
  "locks": {"active": true, "resources": [{"kind": "speaker", "id": "Fail02"}], "ttl_seconds": 600},
  "logCount": 3
}
```

## Common Failure Modes & How to Recover

| Failure        | Symptom                  | Recovery                                                                                                |
|----------------|--------------------------|---------------------------------------------------------------------------------------------------------|
| Unknown jobId  | `status: "not_found"`    | Do not retry blindly. Find a currently-tracked `jobId` with `jobs_list_active` (running) or `jobs_list` (recent). |
| Terminal but stale | Status returns `complete` or `error` but the agent expected `running` | The job finished while you were doing something else — read `result`/`error` and proceed. Don't restart. |
| Class-specific data missing | No `segmentsProcessed` for STT job, etc. | `job_status` returns the generic shape only. For class-specific fields, call the matching `*_status` tool. |

## Agent Reasoning Notes
`job_status` is the right tool when you're writing class-agnostic orchestration code — polling, retry, "is this speaker locked?" checks. For interactive diagnosis of a specific compute pipeline, prefer `compute_status` so you get the structured `result.results.<step>` payload. Treat `not_found` as a hard failure (the job isn't going to appear later); treat `complete` / `error` as terminal and act on them rather than continuing to poll.

## Related Skills
- `compute_status` — richer per-step result payload for compute-class jobs.
- `job_logs` — line-level log retrieval when `error` needs deeper context.
- `jobs_list`, `jobs_list_active` — recover a lost `jobId`.
