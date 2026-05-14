# Job result schema

PARSE compute jobs expose a generic job snapshot while running and a richer `result` object when terminal. This page summarizes the user-facing fields; the full agent schema lives in [MCP schema](../mcp/schema.md#compute-job-result-shapes).

## Generic terminal shape

```json
{
  "jobId": "job_...",
  "type": "stt",
  "status": "complete",
  "progress": 100,
  "message": "complete",
  "result": {}
}
```

Terminal states may include `complete`, `error`, `cancelled`, and partial stage-level outcomes such as `partial` or `partial_cancelled` inside a result payload.

## Long-file fields

| Field | Meaning |
|---|---|
| `chunks[]` | Per-chunk diagnostics for long STT/ORTH jobs. Entries include `idx`, `span`, `status`, and optional `error_code` / `error`. |
| `device` | Effective compute device used by a stage (`cpu`, `cuda`, or `cuda:N`). |
| `duration_sec` | Source audio duration known to the job. |
| `coverage_shrink_warning` | IPA overwrite warning when projected coverage is sharply shorter than existing IPA coverage. |

`chunks[]` is diagnostic job-result data. It is not written into the persisted STT cache; caches continue to store merged `segments[]`.

Short files, concept-window reruns, edited-only reruns, or intentionally disabled chunking may return `chunks: []`. Missing chunk rows are suspicious only for long full-file STT or full-mode ORTH runs where chunking should have applied.

## Consumer guidance
- Treat top-level job status and per-stage result status separately.
- Use chunk spans to identify the interval that needs rerun or manual review.
- Use `device` to diagnose unexpected CPU fallback.
- Inspect `coverage_shrink_warning` before accepting destructive IPA overwrite output.

Related: [Processing long recordings](../user-guides/processing-long-recordings.md) and [Troubleshooting common issues](../troubleshooting/).
