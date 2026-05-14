# run_full_annotation_pipeline

**Category:** Advanced
**Mutability:** mutating (starts a background workflow with STT, forced-align, and IPA steps)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** High
**Estimated Tokens:** ~340 (short) / ~720 (full)

## One-Sentence Summary
Runs the high-level annotation workflow for one speaker — full-speaker STT → forced-align → IPA in `run_mode: "full"`, or a `full_pipeline` compute job scoped to all concept windows / manually-edited windows in the other modes.

## When to Use
- The standard "annotate this speaker end-to-end" case — this is the recommended high-level entry point, not `pipeline_run`.
- New-speaker onboarding flows: after `onboard_speaker_import`, this runs the rest of the annotation chain.
- When you want PARSE to pick sensible defaults across the STT → ortho → IPA chain rather than driving each step by hand.
- For concept-window scoping with a single call (`run_mode: "concept-windows"` or `"edited-only"`) — handles the scoping internally instead of requiring per-step `concept_ids` plumbing.

## When NOT to Use
- For fine-grained step subsets or explicit overwrite control (e.g. just re-running ORTH with overwrites) — use `pipeline_run` directly; it accepts `steps` and `overwrites` arguments.
- When you need batch processing across multiple speakers — this is single-speaker. Loop yourself, or write a higher-level macro.
- Without `pipeline_state_read` first. The workflow will start whatever it can, but you risk burning compute on a speaker missing prerequisites.
- For status polling only — this *starts* work. To poll an existing job, use `compute_status` / `job_status`.

## Parameters

| Parameter      | Type     | Required | Description                                                                                                                          | Default       | Example                            |
|----------------|----------|----------|--------------------------------------------------------------------------------------------------------------------------------------|---------------|------------------------------------|
| speaker_id     | string   | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                                                          | —             | `"Speaker01"`                      |
| concept_list   | string[] | Yes      | Concept IDs used for workflow reporting and final annotation summary filtering. Must be non-empty.                                   | —             | `["12", "13", "14"]`               |
| run_mode       | string   | No       | `full` preserves the legacy speaker-wide STT → forced-align → IPA sequence. `concept-windows` and `edited-only` start a `full_pipeline` job scoped to concept windows. | `"full"`      | `"concept-windows"`                |
| concept_ids    | string[] | No       | Exact concept IDs to scope to. Only meaningful for `concept-windows` / `edited-only`. Omitted in those modes = all concept rows / all edited rows. | (all)         | `["12", "13"]`                     |
| dryRun         | boolean  | No       | Validate inputs and preview the planned workflow without starting jobs.                                                              | `false`       | `true`                             |

## Expected Output
On `dryRun: true`: returns `{ status: "dry_run", speaker_id, concept_list, run_mode, concept_ids, source_wav, stages: [...], progress }`. The `stages` array names each planned step with its tool, status (`"planned"`), and `run_mode`. No jobs are created.

On `dryRun: false`:
- `run_mode: "full"` — starts STT, forced-align, and acoustic IPA sequentially, polling each to terminal state. Returns the workflow summary.
- `run_mode: "concept-windows"` / `"edited-only"` — starts one `full_pipeline` compute job via `pipeline_run`. Returns the `jobId` to poll with `compute_status` (`computeType: "full_pipeline"`).

**Always poll any returned `jobId` to terminal state before claiming success.** For long full-file/full-pipeline runs, inspect `chunks[]`, stage `device`, and IPA `coverage_shrink_warning` in the terminal result before sign-off.

## Example Successful Call
Dry run (concept-windows mode):
```json
{
  "speaker_id": "Speaker01",
  "concept_list": ["12", "13", "14"],
  "run_mode": "concept-windows",
  "concept_ids": ["12", "13"],
  "dryRun": true
}
```

Representative dry-run response:
```json
{
  "readOnly": true,
  "previewOnly": true,
  "dryRun": true,
  "speaker_id": "Speaker01",
  "concept_list": ["12", "13", "14"],
  "run_mode": "concept-windows",
  "concept_ids": ["12", "13"],
  "source_wav": "audio/working/Speaker01/source.wav",
  "stages": [
    {"stage": "stt",   "tool": "pipeline_run", "status": "planned", "run_mode": "concept-windows"},
    {"stage": "ortho", "tool": "pipeline_run", "status": "planned", "run_mode": "concept-windows"},
    {"stage": "ipa",   "tool": "pipeline_run", "status": "planned", "run_mode": "concept-windows"}
  ],
  "progress": {"completedStages": 0, "totalStages": 3, "currentStage": "stt"}
}
```

Legacy full-speaker dry run:
```json
{
  "speaker_id": "Speaker01",
  "concept_list": ["12", "13", "14"],
  "run_mode": "full",
  "dryRun": true
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                                | Recovery                                                                                                              |
|----------------------------------------|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Empty `concept_list`                   | Validation error                                                       | The workflow uses `concept_list` for reporting and summary filtering. Always pass a non-empty array, even if all concepts. |
| Missing source audio                   | Job errors with file-not-found                                         | Run `pipeline_state_read` first. The speaker may not have been imported via `onboard_speaker_import` or normalized.   |
| Step failure mid-workflow (full mode)  | One sub-job ends in `error`, later stages may not run                  | Read `job_logs` on the failed sub-job's `jobId`. Re-start only the failed stage via `pipeline_run` with `steps: [<that_step>]`. |
| Live apply without confirmation        | Workflow starts before user is ready                                   | Always run with `dryRun: true` first, present the `stages` plan, and require explicit confirmation before `dryRun: false`. |
| `concept_ids` references unknown IDs   | Workflow completes but with skipped windows                            | Verify IDs against `project_context_read` / `list_concepts_by_tag` before passing.                                    |

## Agent Reasoning Notes
Treat this as the workflow macro: prefer it over `pipeline_run` for the common case. The `run_mode` choice is load-bearing — `full` is for fresh speakers where you want the whole audio processed; `concept-windows` is for review/re-annotation passes restricted to concept rows; `edited-only` is for cleanup passes after the user has manually adjusted some rows. Always (1) call `pipeline_state_read` to confirm preconditions, (2) call this with `dryRun: true` to see the planned stages, (3) confirm with the user, (4) re-run with `dryRun: false`, then (5) poll any returned `jobId` with `compute_status` until terminal. Inspect step-level results before declaring success — a `complete` status can still hide skipped stages, errored stages, partial chunk failures, or IPA coverage-shrink warnings.

## Related Skills
- `pipeline_run` — lower-level entry point with explicit step subset / overwrite control.
- `pipeline_state_read`, `pipeline_state_batch` — preflight before starting.
- `compute_status`, `job_status` — poll the returned `jobId`.
- `onboard_speaker_import` — the typical predecessor for fresh-speaker flows.
- `job_logs` — diagnose a failed stage.
