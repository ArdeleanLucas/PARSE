---
name: parse-mcp-tool-detect-timestamp-offset
description: "Use PARSE MCP tool `detect_timestamp_offset`: Detect a constant timestamp offset between a speaker's annotation intervals and STT segments for the same audio. Uses monotonic anchor-segment alignment (chosen matches must visit anchors and segments in increasing time order) so false matches to similar-sounding words elsewhere in the recording can't elect the wrong direction. Anchors are sampled across the timeline by quantile by default — pass anchorDistribution='earliest' to use the legacy first-N selection. Read-only; returns offsetSec, confidence, spreadSec, direction, warnings, and the matched anchor↔segment pairs so callers can sanity-check before applying."
version: 1.0.0
source: PARSE MCP catalog
source_generated_at: 2026-05-10T17:37:02Z
license: MIT
tags:
  - parse
  - mcp
  - tool
  - chat
---

# PARSE MCP Tool Skill — `detect_timestamp_offset`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `detect_timestamp_offset` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `detect_timestamp_offset`
- **Skill name:** `parse-mcp-tool-detect-timestamp-offset`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `speaker`
- **`additionalProperties`:** `False`
- **Catalog description:** Detect a constant timestamp offset between a speaker's annotation intervals and STT segments for the same audio. Uses monotonic anchor-segment alignment (chosen matches must visit anchors and segments in increasing time order) so false matches to similar-sounding words elsewhere in the recording can't elect the wrong direction. Anchors are sampled across the timeline by quantile by default — pass anchorDistribution='earliest' to use the legacy first-N selection. Read-only; returns offsetSec, confidence, spreadSec, direction, warnings, and the matched anchor↔segment pairs so callers can sanity-check before applying.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200)
- `sttJobId` (type=string; minLength=1; maxLength=128)
- `nAnchors` (type=integer; minimum=2; maximum=50)
- `bucketSec` (type=number; minimum=0.1; maximum=30.0)
- `minMatchScore` (type=number; minimum=0.0; maximum=1.0)
- `anchorDistribution` (type=string; enum=`quantile`, `earliest`)

### Example request/response

Input for a completed STT job:

```json
{
  "speaker": "<SPEAKER_ID>",
  "sttJobId": "stt-<ID>",
  "nAnchors": 12,
  "bucketSec": 1.0,
  "minMatchScore": 0.56,
  "anchorDistribution": "quantile"
}
```

Representative result payload:

```json
{
  "readOnly": true,
  "speaker": "<SPEAKER_ID>",
  "offsetSec": 2.375,
  "confidence": 0.87,
  "nAnchors": 9,
  "totalAnchors": 12,
  "totalSegments": 184,
  "method": "monotonic_alignment",
  "spreadSec": 0.42,
  "direction": "later",
  "directionLabel": "2.375 s later (toward the end)",
  "anchorDistribution": "quantile",
  "reliable": true,
  "warnings": [],
  "matches": [
    {
      "anchor_index": 0,
      "anchor_text": "water",
      "anchor_start": 12.0,
      "segment_index": 17,
      "segment_text": "water",
      "segment_start": 14.375,
      "score": 0.94,
      "offset_sec": 2.375
    }
  ],
  "annotationPath": "annotations/<SPEAKER_ID>.parse.json"
}
```

Treat non-empty `warnings`, low `confidence`, or high `spreadSec` as a stop sign before passing `offsetSec` to `apply_timestamp_offset`.

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)

### Postconditions advertised by catalog

- The tool returns structured inspection data without mutating project state. (`project_state`, `recommended`)

## Portable setup

Use placeholders instead of machine-specific paths:

```bash
cd <PARSE_REPO>
export PARSE_PROJECT_ROOT=<PROJECT_ROOT>
# Optional when input files live outside the PARSE project root:
export PARSE_EXTERNAL_READ_ROOTS=<ABSOLUTE_READ_ROOT_1>[:<ABSOLUTE_READ_ROOT_2>]
PYTHONPATH=python python3 -m adapters.mcp_adapter --project-root "$PARSE_PROJECT_ROOT"
```

For the HTTP MCP bridge, discover the live schema before calling:

```bash
curl "$PARSE_BASE_URL/api/mcp/tools/detect_timestamp_offset?mode=active"
```

## Workflow

1. **Discover** – Confirm `detect_timestamp_offset` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Quality checklist

- [ ] Live catalog confirms `detect_timestamp_offset` is currently exposed.
- [ ] The current live schema was inspected before constructing arguments.
- [ ] Required arguments were provided and optional result limits were bounded.
- [ ] Dry-run/preview was used first when advertised by the catalog.
- [ ] Any returned `jobId` was polled to terminal state.
- [ ] Any file mutation was independently audited after apply.
- [ ] Evidence recorded the exact argument shape, result summary, and verification path.

## Anti-patterns

- Calling internal helper functions and presenting that as MCP validation.
- Running `python/adapters/mcp_adapter.py` by file path; use `PYTHONPATH=python python3 -m adapters.mcp_adapter`.
- Copying local workstation paths into reusable docs, scripts, or handoffs.
- Treating `ok: true`, preview counts, or dry-run output as proof of durable file mutation.
- Auditing legacy `annotations/<Speaker>.json` when active `.parse.json` annotations exist.
- Reporting before a started job reaches terminal state.
