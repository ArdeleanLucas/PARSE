# audio_normalize_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~160 (short) / ~360 (full)

## One-Sentence Summary
Polls the status, progress, and (on completion) result of a normalize job started by `audio_normalize_start`.

## When to Use
- After every `audio_normalize_start` call, until status reaches `complete` or `error`.
- To pick up an in-flight normalize job after a session restart — combine with `jobs_list_active` to find the `jobId`.
- To inspect the final `result` payload, which carries the normalized WAV path and the measured loudness statistics from ffmpeg's two passes.

## When NOT to Use
- For other class statuses (STT, forced-align, IPA, compute) — each has its own `*_status` tool. Use `job_status` when you don't know the class.
- For log-level diagnosis of a failed normalize job — use `job_logs` for the ffmpeg stderr lines.

## Parameters

| Parameter | Type   | Required | Description                                       | Default | Example                                  |
|-----------|--------|----------|---------------------------------------------------|---------|------------------------------------------|
| jobId     | string | Yes      | Identifier from `audio_normalize_start`. `minLength=1`, `maxLength=128`. | — | `"550e8400-e29b-41d4-a716-446655440000"` |

## Expected Output
Returns `{ jobId, type: "normalize", status, progress, message, error, result, ... }`. On terminal `complete`, `result` includes the working WAV output path and the ffmpeg loudnorm pass-2 measured stats. Treat `complete` and `error` as terminal.

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
| Unknown jobId        | `status: "not_found"` or tool error  | Find the live `jobId` via `jobs_list_active`. Don't re-launch the normalize blindly.|
| Job stuck `running`  | Progress idle past expected duration | Read `job_logs` for the ffmpeg stderr. May indicate a corrupt source.               |
| Job ended `error`    | Terminal `error` with message        | `job_logs` carries the ffmpeg failure. Re-import or re-encode the source as needed. |

## Agent Reasoning Notes
This is the matching status tool for `audio_normalize_start` — use it rather than the generic `job_status` when you want the normalize-specific result payload (loudnorm stats, output path). For class-agnostic orchestration loops, `job_status` works equivalently for this job type but returns the generic shape.

## Related Skills
- `audio_normalize_start` — produces the `jobId` polled here.
- `job_logs` — for ffmpeg-level failure diagnosis.
- `job_status` — class-agnostic alternative.
