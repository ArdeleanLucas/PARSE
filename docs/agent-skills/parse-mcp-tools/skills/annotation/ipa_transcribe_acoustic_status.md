# ipa_transcribe_acoustic_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~160 (short) / ~360 (full)

## One-Sentence Summary
Polls the status and progress of a Tier 3 acoustic IPA job started by `ipa_transcribe_acoustic_start`.

## When to Use
- After every `ipa_transcribe_acoustic_start` call, until status reaches `complete` or `error`.
- To resume tracking an in-flight IPA job after a session restart — recover the `jobId` via `jobs_list_active`.
- To capture the terminal snapshot as audit evidence that the IPA tier was populated.

## When NOT to Use
- For other class statuses — STT has `stt_status` / `stt_word_level_status`, forced-align has `forced_align_status`, normalize has `audio_normalize_status`. Use `job_status` for class-agnostic polling.
- For artifact verification — read the IPA cells back via `annotation_read` to confirm the file was actually populated.

## Parameters

| Parameter | Type   | Required | Description                                       | Default | Example                                  |
|-----------|--------|----------|---------------------------------------------------|---------|------------------------------------------|
| jobId     | string | Yes      | Identifier from `ipa_transcribe_acoustic_start`. `minLength=1`, `maxLength=128`. | — | `"550e8400-e29b-41d4-a716-446655440000"` |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, result, ... }`. Terminal states: `complete` (IPA tier written) or `error`.

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
| Job stuck `running`  | Progress idle past expected duration | Read `job_logs` for the wav2vec2 inference step logs.                               |
| Job ended `error`    | Terminal `error` with message        | `job_logs` carries the failure detail (often GPU/OOM-related).                      |

## Agent Reasoning Notes
This is the matching status tool for `ipa_transcribe_acoustic_start`. After completion, audit the result by calling `annotation_read` with `includeTiers: ["ipa"]` to confirm IPA cells were actually populated — a `complete` status proves the job ran but not that every cell received content (skipped cells, missing audio windows, etc. are possible).

## Related Skills
- `ipa_transcribe_acoustic_start` — produces the `jobId` polled here.
- `annotation_read` — verify IPA cells after completion.
- `pipeline_state_read` — coverage view for the IPA tier.
- `job_logs`, `job_status` — generic alternatives.
