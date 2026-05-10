---
name: parse-mcp-tool-retranscribe-with-boundaries-start
description: "Use PARSE MCP tool `retranscribe_with_boundaries_start`: Start a boundary-constrained STT job for a speaker. Reads the speaker's BND lane (tiers.ortho_words) as authoritative segment boundaries, slices the source audio in memory at each window, and runs faster-whisper on each slice independently. Writes the merged segments to coarse_transcripts/<speaker>.json with source=boundary_constrained. Returns a jobId for polling with retranscribe_with_boundaries_status."
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

# PARSE MCP Tool Skill — `retranscribe_with_boundaries_start`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `retranscribe_with_boundaries_start` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `retranscribe_with_boundaries_start`
- **Skill name:** `parse-mcp-tool-retranscribe-with-boundaries-start`
- **Family:** `chat`
- **Mutability:** `stateful_job`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `speaker`
- **`additionalProperties`:** `False`
- **Catalog description:** Start a boundary-constrained STT job for a speaker. Reads the speaker's BND lane (tiers.ortho_words) as authoritative segment boundaries, slices the source audio in memory at each window, and runs faster-whisper on each slice independently. Writes the merged segments to coarse_transcripts/<speaker>.json with source=boundary_constrained. Returns a jobId for polling with retranscribe_with_boundaries_status.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200)
- `language` (type=string; minLength=0; maxLength=8) — Optional ISO 639-1 language code for faster-whisper. Empty/omitted triggers auto-detect.
- `dryRun` (type=boolean)

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The requested speaker must already have non-empty tiers.ortho_words intervals — boundary-constrained STT slices the audio at those windows and has nothing to do without them. (`project_state`, `required`)

### Postconditions advertised by catalog

- Calling this tool starts or previews a background job that can be polled later. (`job_state`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/retranscribe_with_boundaries_start?mode=active"
```

## Workflow

1. **Discover** – Confirm `retranscribe_with_boundaries_start` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
- For job-backed workflows, record the returned `jobId` and poll until a terminal status before claiming completion.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Quality checklist

- [ ] Live catalog confirms `retranscribe_with_boundaries_start` is currently exposed.
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
