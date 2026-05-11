# pipeline_run

**Category:** Advanced
**Mutability:** mutating (starts a background compute job)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~300 (short) / ~640 (full)

## One-Sentence Summary
Starts a `full_pipeline` compute job for one speaker — the same backend the PARSE UI uses — with explicit control over which subset of `normalize / stt / ortho / ipa` runs and which existing tiers may be overwritten.

## When to Use
- Re-running a single tier on one speaker (e.g. `steps: ["ortho"]` + `overwrites: {ortho: true}` to refresh the ortho tier after changing the configured model).
- Running a specific subset of steps when you don't want the whole STT → ortho → IPA chain (e.g. just STT before manually editing concept windows).
- Targeting concept windows or manually-edited windows only via `run_mode: "concept-windows"` / `"edited-only"` + optional `concept_ids` filter.
- Forcing a language override (`language: "ku"`) when auto-detect picks the wrong language for STT.

## When NOT to Use
- For the standard end-to-end "annotate this whole speaker" flow — use `run_full_annotation_pipeline` instead. It wraps `pipeline_run` with sensible defaults and is the recommended high-level entry point.
- For batch processing across multiple speakers — `pipeline_run` is single-speaker. Iterate manually or write a higher-level macro.
- Without first running `pipeline_state_read` for the target speaker. The preflight tells you which steps `can_run` and whether existing tiers have `full_coverage`; without it you'll fight the step-skip logic blind.

## Parameters

| Parameter   | Type     | Required | Description                                                                                                                                                | Default       | Example                                |
|-------------|----------|----------|------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|----------------------------------------|
| speaker     | string   | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                                                                                | —             | `"Khan01"`                             |
| steps       | string[] | Yes      | Ordered subset of `["normalize", "stt", "ortho", "ipa"]`. Executed in canonical order; the array order is ignored.                                         | —             | `["stt", "ortho", "ipa"]`              |
| overwrites  | object   | No       | Per-step overwrite flags. `false` (default) → skip step if tier is already populated. `true` → replace existing tier data.                                 | `{}`          | `{"ortho": true}`                      |
| language    | string   | No       | Language override for STT + ORTH. Empty/omitted → auto-detect for STT, project default for ORTH. `minLength=1`, `maxLength=32`.                            | (auto/default) | `"sdh"`                                |
| run_mode    | string   | No       | `full` = full-file; `concept-windows` = all concept rows; `edited-only` = manually adjusted concept rows.                                                  | `"full"`      | `"concept-windows"`                    |
| concept_ids | string[] | No       | Exact concept IDs to restrict to. Only meaningful when `run_mode` is `concept-windows` or `edited-only`.                                                   | (all)         | `["1", "2", "3"]`                      |
| dryRun      | boolean  | No       | If `true`, validate inputs and preview the planned compute payload without starting a job.                                                                 | `false`       | `true`                                 |

## Expected Output
On `dryRun: true`: returns `{ status: "dry_run", plan: { speaker, steps, overwrites, language, run_mode, concept_ids }, message }`. No job is created.

On `dryRun: false`: returns `{ jobId, status: "running", speaker, steps, overwrites, computeType: "full_pipeline", run_mode, concept_ids, message }`. **Always poll the returned `jobId` with `compute_status` (set `computeType: "full_pipeline"` for early failure on class mismatch) until status is `complete` or `error` before claiming success.**

Steps run step-resilient: a failing STT will not abort ORTH/IPA for the same speaker — the job completes with per-step `status` inside `result.results`.

## Example Successful Call
Dry run (always do this first):
```json
{
  "speaker": "Khan01",
  "steps": ["normalize", "stt", "ortho", "ipa"],
  "overwrites": {"ortho": true, "ipa": true},
  "language": "sdh",
  "run_mode": "concept-windows",
  "concept_ids": ["1", "2", "3"],
  "dryRun": true
}
```

Live start (same payload, `dryRun: false`) returns:
```json
{
  "jobId": "9b662f0e-9dcf-4faa-9de2-a11f9b9d4de5",
  "status": "running",
  "speaker": "Khan01",
  "steps": ["normalize", "stt", "ortho", "ipa"],
  "overwrites": {"ortho": true, "ipa": true},
  "computeType": "full_pipeline",
  "run_mode": "concept-windows",
  "concept_ids": ["1", "2", "3"],
  "message": "Pipeline job started. Poll with compute_status."
}
```

## Common Failure Modes & How to Recover

| Failure                          | Symptom                                                  | Recovery                                                                                                       |
|----------------------------------|----------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| Step silently skipped            | `result.results.<step>.status: "skipped"`                | The tier was already populated and `overwrites[<step>]` was not `true`. Set the flag and re-run that step only. |
| Speaker missing required file    | Job errors with "no source audio" or "ortho tier empty"  | Run `pipeline_state_read` first — `can_run: false` rows include a `reason` string explaining the gap.          |
| Wrong language detected (STT)    | STT output garbled / low confidence                      | Re-run with explicit `language: "<iso>"`. Use `overwrites: {stt: true}` to replace the prior result.           |
| `concept_ids` referenced unknown IDs | Job completes but `result.summary.skipped` matches IDs | Verify IDs against `project_context_read` (`concepts` section) or `list_concepts_by_tag`. Drop unknown IDs and re-run. |
| Lock conflict                    | Job rejected because speaker resource is held by another active job | Wait for the conflicting job to terminate, or check `jobs_list_active` to find it.                  |

## Agent Reasoning Notes
`pipeline_run` is the right tool when you need *fine control* — exact step subset, explicit overwrites, language override, concept-window scoping. For the common "just annotate this speaker end-to-end" case, prefer `run_full_annotation_pipeline` and let it pick sensible defaults. Always preface a live call with (1) `pipeline_state_read` to see what `can_run` and what already has `full_coverage`, and (2) a `dryRun: true` of the exact payload to confirm the plan. After live start, poll `compute_status` with `computeType: "full_pipeline"` until terminal, then inspect `result.summary` and `result.results.<step>.status` — a top-level `complete` can still hide step-level errors.

## Related Skills
- `run_full_annotation_pipeline` — higher-level workflow macro; prefer for common cases.
- `pipeline_state_read`, `pipeline_state_batch` — preflight before starting.
- `compute_status` — poll the returned `jobId`.
- `job_logs` — diagnose a failed or stalled pipeline step.
