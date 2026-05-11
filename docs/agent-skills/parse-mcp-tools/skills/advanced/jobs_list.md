# jobs_list

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only listing)
**Complexity:** Low
**Estimated Tokens:** ~220 (short) / ~480 (full)

## One-Sentence Summary
Lists jobs from the PARSE job registry — active and recently completed — with optional filtering by status, type, and speaker, plus a bounded result limit.

## When to Use
- Recovering a `jobId` you lost (session restart, agent crashed mid-poll, chat lost the start-call response).
- Auditing recent activity on a speaker (`speaker: "Khan01"` to scope).
- Finding all jobs of a given class — e.g. all `compute:full_pipeline` jobs to compare success counts across speakers.
- Distinguishing recently-finished from currently-running work when triaging a project (`statuses: ["complete", "error"]` for the last batch).

## When NOT to Use
- For "what's running *right now*?" — `jobs_list_active` is purpose-built for that and takes no arguments. `jobs_list` returns completed/error jobs in its dwell window too, which is often noise for liveness checks.
- For the detailed snapshot of a single known job — use `job_status` or `compute_status` directly with the `jobId`.
- As a substitute for log retention. The registry is bounded; jobs age out. Don't rely on `jobs_list` to answer "what happened last week".

## Parameters

| Parameter | Type     | Required | Description                                                                                  | Default       | Example                              |
|-----------|----------|----------|----------------------------------------------------------------------------------------------|---------------|--------------------------------------|
| statuses  | string[] | No       | Filter by status. Accepts `queued`, `running`, `complete`, `error`.                          | (all)         | `["running", "queued"]`              |
| types     | string[] | No       | Filter by job class — e.g. `"compute:full_pipeline"`, `"stt"`, `"onboard:speaker_import"`.   | (all)         | `["compute:full_pipeline"]`          |
| speaker   | string   | No       | Restrict to jobs whose meta names this speaker. `minLength=1`, `maxLength=200`.              | (all)         | `"Khan01"`                           |
| limit     | integer  | No       | Cap on result count. `minimum=1`, `maximum=500`.                                             | (server default) | `50`                              |

## Expected Output
Returns `{ jobs: [...], count, mode, previewOnly }`. Each entry in `jobs` carries `jobId`, `type`, `status`, `progress`, `message`, `meta`, `done`, `success`, `logCount`. The set is the union of currently-active jobs and recently-completed jobs still in the registry's dwell window.

Does not mutate project state.

## Example Successful Call
```json
{
  "statuses": ["running", "queued"],
  "types": ["compute:full_pipeline"],
  "speaker": "Khan01",
  "limit": 5
}
```

Representative response:
```json
{
  "readOnly": true,
  "jobs": [
    {
      "jobId": "9df2d820-4f7d-4f02-a6b0-2eb4e33f5c8a",
      "type": "compute:full_pipeline",
      "status": "running",
      "progress": 42.5,
      "message": "Running ORTH for Khan01",
      "meta": {"speaker": "Khan01", "language": "sdh"},
      "done": false,
      "success": false,
      "logCount": 7
    }
  ],
  "count": 1,
  "mode": "read-only",
  "previewOnly": true
}
```

## Common Failure Modes & How to Recover

| Failure                            | Symptom                                                | Recovery                                                                                            |
|------------------------------------|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Job aged out of registry           | Expected `jobId` not in results despite recent run     | The dwell window has passed. There is no recovery for the snapshot itself — rely on persisted artifacts for evidence of past work. |
| Wrong `types` string               | Empty result despite knowing jobs of that class exist  | Type strings are exact (e.g. `compute:full_pipeline`, not `full_pipeline`). Drop the `types` filter and inspect a row's `type` to learn the canonical value. |
| Limit too low                      | Pagination truncation                                  | Increase `limit` up to 500, or filter more tightly with `statuses`/`types`/`speaker`.               |

## Agent Reasoning Notes
Use `jobs_list` for discovery and audit, `jobs_list_active` for liveness, and `job_status`/`compute_status` for the single-job detail. When in doubt about a job class, do an unfiltered `jobs_list` and read `type` off a representative row before adding `types` filters — this avoids the silent empty-result trap from typos. Filter aggressively when a project has hundreds of jobs in the registry; the default `limit` won't necessarily show you what you want.

## Related Skills
- `jobs_list_active` — narrower: only currently-running jobs, no arguments needed.
- `job_status`, `compute_status` — per-job detail once you have a `jobId`.
- `job_logs` — line-level log retrieval.
