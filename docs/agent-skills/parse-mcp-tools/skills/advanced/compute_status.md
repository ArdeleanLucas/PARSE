# compute_status

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~220 (short) / ~520 (full)

## One-Sentence Summary
Polls a PARSE compute job (full_pipeline, ortho, ipa, contact-lexemes, etc.) by `jobId` and returns its current snapshot, with per-step results and counts when the job is complete.

## When to Use
- After any compute-class start call (`pipeline_run`, `run_full_annotation_pipeline`, and the lower-level ortho/ipa/contact-lexeme starters) — poll here until a terminal status before claiming success.
- To watch progress on a long-running pipeline without re-reading project files.
- To inspect per-step success/skip/error counts for `full_pipeline` jobs.
- As a `computeType`-guarded poll when you want the call to fail fast if the `jobId` belongs to a different job class.

## When NOT to Use
- For non-compute job classes — STT, IPA-acoustic, audio-normalize, forced-align, compute-boundaries, retranscribe — each has its own dedicated `*_status` tool. Use `job_status` when you don't know the class.
- To audit the *files* a job wrote. The `result` payload is a summary; for ground truth, read `annotations/<speaker>.parse.json` (or the relevant artifact) back independently.
- For failure diagnosis. The snapshot exposes `error` but not per-step log lines — reach for `job_logs` when a job ended in error.

## Parameters

| Parameter   | Type   | Required | Description                                                                                                                       | Default          | Example          |
|-------------|--------|----------|-----------------------------------------------------------------------------------------------------------------------------------|------------------|------------------|
| jobId       | string | Yes      | Job identifier returned by the start tool. `minLength=1`, `maxLength=128`.                                                        | —                | `"compute-7f3a"` |
| computeType | string | No       | Expected compute type (e.g. `"full_pipeline"`). When set, the tool validates the job's type matches before returning the snapshot. | (no validation)  | `"full_pipeline"` |

## Expected Output
Returns a JSON snapshot:

- `jobId`, `type` — identifiers from the original start call.
- `status` — one of `queued`, `running`, `complete`, `error`, `invalid_job_type`.
- `progress` — 0–100.
- `message`, `error` — current human-readable state; `error` is `null` until the job fails.
- `result` — present once `status == "complete"`. For pipeline jobs:
  - `result.steps_run` — ordered list of step names.
  - `result.results.<step>` — `{ status, filled, ... }` per step.
  - `result.summary` — aggregate counts: `{ ok, skipped, error }`.

Does not mutate project state.

## Example Successful Call
```json
{
  "jobId": "compute-7f3a",
  "computeType": "full_pipeline"
}
```

Representative completed response:
```json
{
  "readOnly": true,
  "jobId": "compute-7f3a",
  "type": "compute:full_pipeline",
  "status": "complete",
  "progress": 100.0,
  "message": "Compute complete",
  "error": null,
  "result": {
    "speaker": "<SPEAKER_ID>",
    "steps_run": ["ortho", "ipa"],
    "results": {
      "ortho": {"status": "ok", "filled": 128},
      "ipa":   {"status": "ok", "filled": 129}
    },
    "summary": {"ok": 2, "skipped": 0, "error": 0}
  }
}
```

## Common Failure Modes & How to Recover

| Failure                                    | Symptom                                                | Recovery                                                                                                          |
|--------------------------------------------|--------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| Wrong job class                            | `status: "invalid_job_type"`                           | The `jobId` is from a non-compute job. Drop the `computeType` arg, switch to the matching `*_status`, or use `job_status`. |
| Unknown jobId                              | Tool error: jobId not found                            | Confirm the start call actually returned a `jobId` (don't fabricate). Use `jobs_list` / `jobs_list_active` to find currently known jobs. |
| Job stuck `running`                        | `progress` hasn't advanced past the expected duration  | Read `job_logs` for the same `jobId`. For pipeline jobs, inspect `result.results.<step>` (visible mid-run) to pinpoint the stalled step. |
| Step-level error inside a `complete` job   | `status: "complete"` but `result.summary.error > 0`    | A pipeline can finish without raising. Read `result.results.<step>.status` and re-run only the failed step instead of the whole pipeline. |

## Agent Reasoning Notes
This is the canonical "is it done yet?" tool for *compute-class* jobs. Every call to `pipeline_run`, `run_full_annotation_pipeline`, or a lower-level ortho/ipa/contact-lexeme starter should be followed by polling here until `status` reaches a terminal value (`complete` or `error`). For pipeline jobs, the load-bearing information lives in `result.summary` and `result.results.<step>` — a `complete` top-level status can still hide step-level errors, so always look at the summary counts before declaring success. Pair with `job_logs` for failure diagnosis and with the generic `job_status` when polling a job whose class you don't know in advance.

## Related Skills
- `pipeline_run`, `run_full_annotation_pipeline` — typical producers of `jobId`s polled here.
- `job_status` — class-agnostic alternative; use when the job class is unknown.
- `job_logs` — line-level log retrieval for failure diagnosis.
- `jobs_list`, `jobs_list_active` — find a `jobId` when the producing call's return was lost.
