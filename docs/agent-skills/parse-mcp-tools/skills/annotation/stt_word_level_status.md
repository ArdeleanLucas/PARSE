# stt_word_level_status

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only poll)
**Complexity:** Low
**Estimated Tokens:** ~200 (short) / ~430 (full)

## One-Sentence Summary
Polls a Tier 1 word-level STT job started by `stt_word_level_start`, optionally returning a bounded preview of segments and their nested `words[]` payload.

## When to Use
- After every `stt_word_level_start` call, until status reaches `complete` or `error`.
- To inspect a sample of segments + word timestamps without reading the full cache file.
- To resume tracking after a session restart — combine with `jobs_list_active` to recover the `jobId`.
- For audit evidence — the response shape distinguishes word-level output (`words[]` present) from plain sentence-level STT.

## When NOT to Use
- For plain sentence-level STT — use `stt_status` (no `words[]`).
- For other class statuses (forced-align, IPA, normalize, BND, retranscribe) — use their paired `*_status` tools.
- For the full segment dump on a long recording — `maxSegments` caps at 300. Read the cache file via `read_text_preview` for more.

## Parameters

| Parameter       | Type    | Required | Description                                                                  | Default       | Example                                  |
|-----------------|---------|----------|------------------------------------------------------------------------------|---------------|------------------------------------------|
| jobId           | string  | Yes      | Identifier from `stt_word_level_start`. `minLength=1`, `maxLength=128`.      | —             | `"550e8400-e29b-41d4-a716-446655440000"` |
| includeSegments | boolean | No       | If `true`, include a segment preview in the response.                        | `false`       | `true`                                   |
| includeWords    | boolean | No       | If `true` (and `includeSegments: true`), each segment carries the `words[]` array. | `false`       | `true`                                   |
| maxSegments     | integer | No       | Cap on returned segments when `includeSegments: true`. `minimum=1`, `maximum=300`. | (server default) | `50`                                   |

## Expected Output
Returns `{ jobId, type, status, progress, message, error, result, segments?, ... }`. Terminal states: `complete` (cache written with word timestamps) or `error`. When `includeSegments: true`, `segments` contains the bounded preview; when `includeWords: true`, each segment includes `words: [{ word, start, end, prob }, ...]`. Terminal `result` can include MC-384 fields: `chunks[]` for long-file chunk diagnostics, `duration_sec`, and `device`.

Does not mutate project state.

## Example Successful Call
Plain status:
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000"
}
```

Segment + word preview:
```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "includeSegments": true,
  "includeWords": true,
  "maxSegments": 20
}
```

## Common Failure Modes & How to Recover

| Failure                       | Symptom                                                  | Recovery                                                                            |
|-------------------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------|
| Unknown jobId                 | `status: "not_found"` or tool error                      | Find the live `jobId` via `jobs_list_active`.                                       |
| Job stuck `running`           | Progress idle past expected duration                     | Read `job_logs`.                                                                    |
| Job ended `error`             | Terminal `error` with message                             | `job_logs` carries the failure detail.                                              |
| `includeWords` but no words[] | `includeWords: true` but segments have no nested array   | The cache may be from `stt_start` (sentence-level) rather than this tool. Verify via `result.source` or re-run word-level.|

## Agent Reasoning Notes
For long recordings, keep the default 10-minute STT chunks unless a specific failure requires smaller chunks; do not disable chunking for ordinary fieldwork. Inspect terminal `result.chunks[]` and `job_logs` before rerunning blindly.

This is the matching status tool for `stt_word_level_start`. Use `includeSegments: true` + `includeWords: true` for spot-checks of Tier 1 word boundaries — but for full-recording inspection read the cache file via `read_text_preview` instead. After completion, the cache feeds Tier 2 forced-align or `compute_boundaries_start`.

## Related Skills
- `stt_word_level_start` — produces the `jobId` polled here.
- `stt_status` — sentence-level alternative.
- `forced_align_start`, `compute_boundaries_start` — Tier 2 follow-ups that consume the cache.
- `job_logs`, `job_status` — generic alternatives.
