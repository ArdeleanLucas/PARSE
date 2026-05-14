# stt_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~170 (short) / ~370 (full)

## One-Sentence Summary
Polls the status and progress of an existing STT job (`stt_start`), optionally returning a bounded preview of segments.

## When to Use
- After every `stt_start` call, until status reaches `complete` or `error`.
- To inspect a sample of segments (`includeSegments: true`, `maxSegments`) without re-running STT.
- To resume tracking an in-flight STT job after a session restart — combine with `jobs_list_active` to recover the `jobId`.

## When NOT to Use
- For word-level STT — that's `stt_word_level_status`, which returns nested `words[]` arrays.
- For other class statuses (forced-align, IPA, normalize, BND, retranscribe) — each has its own paired `*_status`. Use `job_status` if you don't know the class.
- For the full segment dump on a long recording — `maxSegments` caps at 300. For more, read `coarse_transcripts/<speaker>.json` directly via `read_text_preview` (with bounds).

## Parameters

| Parameter       | Type    | Required | Description                                                                  | Default       | Example                                  |
|-----------------|---------|----------|------------------------------------------------------------------------------|---------------|------------------------------------------|
| jobId           | string  | Yes      | Identifier from `stt_start`. `minLength=1`, `maxLength=128`.                 | —             | `"550e8400-e29b-41d4-a716-446655440000"` |
| includeSegments | boolean | No       | If `true`, include a segment preview in the response.                        | `false`       | `true`                                   |
| maxSegments     | integer | No       | Cap on returned segments when `includeSegments: true`. `minimum=1`, `maximum=300`. | (server default) | `50`                                   |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, result, segments?, ... }`. Terminal states: `complete` (cache written to `coarse_transcripts/<speaker>.json`) or `error`. With `includeSegments: true`, `segments` is the bounded preview list (each segment carries `start_sec`, `end_sec`, `text`). Terminal `result` can include MC-384 fields: `chunks[]` for long-file chunk diagnostics, `duration_sec`, and `device`.

Does not mutate project state.

## Example Successful Call
Plain status:
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000"
}
```

Status with segment preview:
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "includeSegments": true,
  "maxSegments": 50
}
```

## Common Failure Modes & How to Recover

| Failure              | Symptom                                                  | Recovery                                                                            |
|----------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------|
| Unknown jobId        | `status: "not_found"` or tool error                      | Find the live `jobId` via `jobs_list_active`.                                       |
| Job stuck `running`  | Progress idle past expected duration                     | Read `job_logs` for the faster-whisper inference step logs.                         |
| Job ended `error`    | Terminal `error` with message                             | `job_logs` carries CUDA/OOM/decode-error detail.                                    |
| Segment preview truncated | `segments` length matches `maxSegments`              | Increase `maxSegments` (up to 300), or read the cache file via `read_text_preview`. |

## Agent Reasoning Notes
For long recordings, keep the default 10-minute STT chunks unless a specific failure requires smaller chunks; do not disable chunking for ordinary fieldwork. Inspect terminal `result.chunks[]` and `job_logs` before rerunning blindly.

This is the matching status tool for `stt_start`. Use `includeSegments: true` only for spot-checks; the cache file is the canonical source. For the standard Tier 1 → 2 → 3 pipeline, prefer `stt_word_level_status` since that's where downstream forced-align starts.

## Related Skills
- `stt_start` — produces the `jobId` polled here.
- `stt_word_level_status` — word-level alternative.
- `job_logs`, `job_status` — generic alternatives.
