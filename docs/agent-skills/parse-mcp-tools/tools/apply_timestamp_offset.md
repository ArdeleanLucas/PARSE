---
name: parse-mcp-tool-apply-timestamp-offset
description: "Use PARSE MCP tool `apply_timestamp_offset`: Shift every annotation interval (start and end) by offsetSec for the given speaker. Mutates annotations/<speaker>.parse.json. Use dryRun=true first to preview the shift, then dryRun=false to write."
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

# PARSE MCP Tool Skill — `apply_timestamp_offset`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `apply_timestamp_offset` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `apply_timestamp_offset`
- **Skill name:** `parse-mcp-tool-apply-timestamp-offset`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `speaker`, `offsetSec`, `dryRun`
- **`additionalProperties`:** `False`
- **Catalog description:** Shift every annotation interval (start and end) by offsetSec for the given speaker. Mutates annotations/<speaker>.parse.json. Use dryRun=true first to preview the shift, then dryRun=false to write.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200) — Speaker ID whose annotation intervals will be shifted.
- `offsetSec` (type=number) — Seconds to add to every interval start/end; negative values pull timestamps earlier.
- `dryRun` (type=boolean) — If true, preview the timestamp shift without writing annotations/<speaker>.parse.json.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The target speaker must already have an annotation file under annotations/. (`file_presence`, `required`)

### Postconditions advertised by catalog

- When dryRun=false, the speaker's annotation intervals are rewritten with the requested offset. (`filesystem_write`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/apply_timestamp_offset?mode=active"
```

## Workflow

1. **Discover** – Confirm `apply_timestamp_offset` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Quality checklist

- [ ] Live catalog confirms `apply_timestamp_offset` is currently exposed.
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
