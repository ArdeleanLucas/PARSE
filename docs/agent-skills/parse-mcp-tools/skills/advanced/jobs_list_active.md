# jobs_list_active

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only listing)
**Complexity:** Low
**Estimated Tokens:** ~190 (short) / ~440 (full)

## One-Sentence Summary
Lists all currently-running PARSE jobs (STT, normalize, compute, onboard, forced-align, IPA, etc.) with no arguments — the canonical "what's PARSE doing right now?" check.

## When to Use
- Recovering live `jobId`s after a session restart, agent crash, or lost chat context.
- Liveness probe before starting new work — e.g. detecting that an STT or compute job is already underway on a target speaker.
- Project-wide activity audit in chat-driven flows ("am I waiting on anything before I close this session?").
- Detecting stuck jobs — combine with `job_logs` on each returned `jobId` to find one whose `progress` hasn't moved.

## When NOT to Use
- For *historical* job listings (completed, error, recent successes) — use `jobs_list` with `statuses` filters.
- For the detail of a single known job — use `job_status` or `compute_status`.
- To check if a *specific* job is still running. `job_status` answers that directly; `jobs_list_active` is a list-pull and may not include terminal jobs once they leave the dwell window.

## Parameters
No parameters. Pass `{}`.

## Expected Output
Returns `{ jobs: [...], count, mode, previewOnly }`. Each `jobs` entry includes `jobId`, `type`, `status`, `progress`, `result` (typically `null` while running), `startedTs`, `message`, optional class-specific counters (`segmentsProcessed` / `totalSegments` for STT), `locks`, `done`, `success`, `speaker`, `language`.

**Important:** Terminal jobs (`complete` / `error`) may briefly appear here during the active-job dwell window so the UI and agents can render completion chips after a reload. Don't treat presence in this list as a strict guarantee of `status: "running"` — read each row's `status` field directly.

Does not mutate project state.

## Example Successful Call
```json
{}
```

Representative response:
```json
{
  "readOnly": true,
  "jobs": [
    {
      "jobId": "b38f8a2d-b29f-4f17-a4ac-8b7e8c4b1a6d",
      "type": "stt",
      "status": "running",
      "progress": 50.0,
      "result": null,
      "startedTs": 1778436000.0,
      "message": "Halfway there",
      "segmentsProcessed": 12,
      "totalSegments": 24,
      "locks": {"active": true, "resources": ["speaker:Khan01"]},
      "done": false,
      "success": false,
      "speaker": "Khan01",
      "language": "sdh"
    }
  ],
  "count": 1,
  "mode": "read-only",
  "previewOnly": true
}
```

## Common Failure Modes & How to Recover

| Failure                                 | Symptom                                            | Recovery                                                                                       |
|-----------------------------------------|----------------------------------------------------|------------------------------------------------------------------------------------------------|
| Includes terminal jobs in dwell window  | Job has `status: "complete"` but still listed      | Filter on `status == "running"` client-side, or pivot to `jobs_list` with explicit `statuses`. |
| Empty result when work is genuinely happening | `count: 0` but the project is mid-pipeline    | The job may have finished between calls or the registry was rotated. Use `jobs_list` (with completed statuses) to confirm. |
| Lock conflict before starting new work  | Active job already holds `speaker:<id>` resource   | Either wait for the existing job to terminate, or scope the new work to a different speaker.   |

## Agent Reasoning Notes
This is the cheapest way to recover orchestration state after a restart — one call, no arguments, returns everything currently live. Pair with `job_status` to drill into each entry. The dwell window means you can't use this as a strict "is anything running?" test on its own (terminal jobs appear briefly); always check each row's `status`. For longer-horizon audit (completed jobs, error chains, who ran what when), reach for `jobs_list`.

## Related Skills
- `jobs_list` — broader registry queries with status/type/speaker filters.
- `job_status`, `compute_status` — per-job detail once you have a `jobId` from this list.
- `job_logs` — diagnose a stuck active job.
