---
name: parse-mcp-tool-peaks-generate
description: "Use PARSE MCP tool `peaks_generate`: Generate waveform peak data for a speaker's audio and write to peaks/<speaker>.json (or a custom outputPath). Required for the waveform visualiser after audio changes. Provide speaker or audioPath."
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

# PARSE MCP Tool Skill — `peaks_generate`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `peaks_generate` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `peaks_generate`
- **Skill name:** `parse-mcp-tool-peaks-generate`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** None
- **`additionalProperties`:** `False`
- **Catalog description:** Generate waveform peak data for a speaker's audio and write to peaks/<speaker>.json (or a custom outputPath). Required for the waveform visualiser after audio changes. Provide speaker or audioPath.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200) — Speaker ID — resolves audio from annotations.
- `audioPath` (type=string; minLength=1; maxLength=512) — Explicit audio file path (absolute or project-relative). Overrides speaker lookup.
- `outputPath` (type=string; minLength=1; maxLength=512) — Where to write peaks JSON. Defaults to peaks/<speaker>.json.
- `samplesPerPixel` (type=integer; minimum=64; maximum=8192) — Samples per waveform pixel (default 512).
- `dryRun` (type=boolean) — Compute peaks but do not write to disk.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)

### Postconditions advertised by catalog

- When the tool is not in preview mode, it writes or updates a project artifact. (`filesystem_write`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/peaks_generate?mode=active"
```

## Workflow

1. **Discover** – Confirm `peaks_generate` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Dry-run peaks preview example

Use dry-run to confirm the resolved audio and waveform size before writing `peaks/<speaker>.json`:

```bash
curl -s -X POST "$PARSE_BASE_URL/api/mcp/tools/peaks_generate?mode=active" \
  -H 'Content-Type: application/json' \
  --data '{"speaker":"Khan01","samplesPerPixel":512,"dryRun":true}'
```

Expected preview output:

```json
{
  "tool": "peaks_generate",
  "ok": true,
  "result": {
    "readOnly": true,
    "previewOnly": true,
    "sampleRate": 44100,
    "samplesPerPixel": 512,
    "totalSamples": 5292000,
    "peakCount": 10336,
    "durationSec": 120.0,
    "mode": "read-only"
  }
}
```

A live write uses the same arguments with `"dryRun": false` and returns `success`, `outputPath`, `sampleRate`, `samplesPerPixel`, `totalSamples`, `peakCount`, and `durationSec`.

## Quality checklist

- [ ] Live catalog confirms `peaks_generate` is currently exposed.
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
