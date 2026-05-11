---
name: parse-mcp-tool-spectrogram-preview
description: "Use PARSE MCP tool `spectrogram_preview`: Read-only placeholder/backend hook for spectrogram preview requests. Validates bounds and reports capability status."
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

# PARSE MCP Tool Skill — `spectrogram_preview`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `spectrogram_preview` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `spectrogram_preview`
- **Skill name:** `parse-mcp-tool-spectrogram-preview`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `sourceWav`, `startSec`, `endSec`
- **`additionalProperties`:** `False`
- **Catalog description:** Read-only placeholder/backend hook for spectrogram preview requests. Validates bounds and reports capability status.

### Parameters

- `sourceWav` (type=string; minLength=1; maxLength=512)
- `startSec` (type=number; minimum=0.0)
- `endSec` (type=number; minimum=0.0)
- `windowSize` (type=integer; enum=`256`, `512`, `1024`, `2048`, `4096`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/spectrogram_preview?mode=active"
```

## Workflow

1. **Discover** – Confirm `spectrogram_preview` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Worked example

A valid preview request must stay within project audio roots and use `endSec > startSec`:

```bash
curl -sS -X POST "$PARSE_BASE_URL/api/mcp/tools/spectrogram_preview?mode=active" \
  -H "Content-Type: application/json" \
  --data '{
    "sourceWav": "audio/working/Speaker01/source.wav",
    "startSec": 10.0,
    "endSec": 14.5,
    "windowSize": 2048
  }'
```

Equivalent MCP arguments:

```json
{
  "sourceWav": "audio/working/Speaker01/source.wav",
  "startSec": 10.0,
  "endSec": 14.5,
  "windowSize": 2048
}
```

Current placeholder response shape:

```json
{
  "tool": "spectrogram_preview",
  "ok": true,
  "result": {
    "readOnly": true,
    "previewOnly": true,
    "status": "placeholder",
    "message": "Spectrogram preview backend hook acknowledged, but binary/image generation is not wired in this MVP.",
    "request": {
      "sourceWav": "audio/working/Speaker01/source.wav",
      "startSec": 10.0,
      "endSec": 14.5,
      "windowSize": 2048
    },
    "backendHook": {
      "implemented": false,
      "plannedEndpoint": "/api/compute/spectrograms",
      "notes": "Client-side spectrogram worker remains the active rendering path."
    },
    "mode": "read-only"
  }
}
```

## Quality checklist

- [ ] Live catalog confirms `spectrogram_preview` is currently exposed.
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
