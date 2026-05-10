---
name: parse-mcp-tool-transcript-reformat
description: "Use PARSE MCP tool `transcript_reformat`: Reformat a *_coarse.json alignment file into PARSE CoarseTranscript schema (speaker, source_wav, duration_sec, segments[]). Without outputPath returns the reformatted JSON object; with outputPath writes inside the project."
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

# PARSE MCP Tool Skill — `transcript_reformat`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `transcript_reformat` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `transcript_reformat`
- **Skill name:** `parse-mcp-tool-transcript-reformat`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `inputPath`
- **`additionalProperties`:** `False`
- **Catalog description:** Reformat a *_coarse.json alignment file into PARSE CoarseTranscript schema (speaker, source_wav, duration_sec, segments[]). Without outputPath returns the reformatted JSON object; with outputPath writes inside the project.

### Parameters

- `inputPath` (type=string; minLength=1; maxLength=512) — Path to the *_coarse.json file to reformat (absolute or project-relative).
- `outputPath` (type=string; minLength=1; maxLength=512) — Project-relative or absolute path inside project root to write the result.
- `speaker` (type=string; minLength=1; maxLength=200) — Override speaker ID (inferred from filename if omitted).
- `sourceWav` (type=string; minLength=1; maxLength=512) — Override source WAV path written into the output metadata.
- `durationSec` (type=number; minimum=0.0) — Override total duration in seconds (inferred from segments if omitted).
- `dryRun` (type=boolean) — Return parsed JSON without writing.

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
curl "$PARSE_BASE_URL/api/mcp/tools/transcript_reformat?mode=active"
```

## Workflow

1. **Discover** – Confirm `transcript_reformat` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Quality checklist

- [ ] Live catalog confirms `transcript_reformat` is currently exposed.
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
