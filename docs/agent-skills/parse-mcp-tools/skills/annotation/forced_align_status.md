# forced_align_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~160 (short) / ~360 (full)

## One-Sentence Summary
Polls the status and progress of a Tier 2 forced-alignment job started by `forced_align_start`.

## When to Use
- After every `forced_align_start` call, until status reaches `complete` or `error`.
- To resume tracking an in-flight Tier 2 job after a session restart (find the `jobId` via `jobs_list_active`).
- To capture the terminal snapshot as audit evidence — the result payload carries the per-word alignment summary.

## When NOT to Use
- For other class statuses — STT has `stt_status` / `stt_word_level_status`, IPA has `ipa_transcribe_acoustic_status`, normalize has `audio_normalize_status`. Use `job_status` if you don't know.
- For artifact verification ("did the file actually update?") — read the annotation file back via `annotation_read` for the Tier 2 boundary intervals.

## Parameters

| Parameter | Type   | Required | Description                                       | Default | Example                                  |
|-----------|--------|----------|---------------------------------------------------|---------|------------------------------------------|
| jobId     | string | Yes      | Identifier from `forced_align_start`. `minLength=1`, `maxLength=128`. | — | `"550e8400-e29b-41d4-a716-446655440000"` |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, result, ... }`. Terminal states: `complete` (alignment written) or `error`.

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
| Job stuck `running`  | Progress idle past expected duration | Read `job_logs` — forced-align logs which word window it's on.                      |
| Job ended `error`    | Terminal `error` with message        | `job_logs` carries CTC/CUDA failure detail.                                         |

## Agent Reasoning Notes
This is the matching status tool for `forced_align_start`. Use it instead of `job_status` when you want forced-align-specific result fields. After completion, verify the speaker's alignment via `annotation_read` (check `tiers.ortho_words` or Tier 2 intervals) and `pipeline_state_read.ortho.full_coverage`.

## Related Skills
- `forced_align_start` — produces the `jobId` polled here.
- `annotation_read`, `pipeline_state_read` — verify the alignment artifact after completion.
- `job_logs`, `job_status` — generic alternatives.
