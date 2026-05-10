---
name: parse-mcp-tool-run-full-annotation-pipeline
description: "Use PARSE MCP tool `run_full_annotation_pipeline`: Run the high-level annotation workflow for one speaker. In run_mode='full' it preserves the legacy speaker-wide STT → forced-align → IPA sequence; in concept-scoped modes it starts one full_pipeline compute job restricted to all concept windows or manually edited concept windows."
version: 1.0.0
source: PARSE MCP catalog
source_generated_at: 2026-05-10T17:37:02Z
license: MIT
tags:
  - parse
  - mcp
  - tool
  - workflow
---

# PARSE MCP Tool Skill — `run_full_annotation_pipeline`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `run_full_annotation_pipeline` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `run_full_annotation_pipeline`
- **Skill name:** `parse-mcp-tool-run-full-annotation-pipeline`
- **Family:** `workflow`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `speaker_id`, `concept_list`
- **`additionalProperties`:** `False`
- **Catalog description:** Run the high-level annotation workflow for one speaker. In run_mode='full' it preserves the legacy speaker-wide STT → forced-align → IPA sequence; in concept-scoped modes it starts one full_pipeline compute job restricted to all concept windows or manually edited concept windows.

### Parameters

- `speaker_id` (type=string; minLength=1; maxLength=200)
- `concept_list` (type=array) — Concept IDs used for workflow reporting and final annotation summary filtering.
- `run_mode` (type=string; default="full"; enum=`full`, `concept-windows`, `edited-only`) — full preserves the legacy speaker-wide path; concept-windows and edited-only run the backend compute pipeline on concept windows.
- `concept_ids` (type=array) — Optional exact concept IDs for scoped run modes. When omitted, concept-windows selects all concept rows and edited-only selects manually adjusted rows.
- `dryRun` (type=boolean) — Validate inputs and preview the planned workflow without starting jobs.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The requested speaker must resolve to a readable source audio file. (`file_presence`, `required`)
- The caller must provide a non-empty concept_list for workflow reporting. (`input_shape`, `required`)

### Postconditions advertised by catalog

- When dryRun=false, STT, forced alignment, and acoustic IPA are each started and polled to a terminal status. (`job_state`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/run_full_annotation_pipeline?mode=active"
```

## Workflow

1. **Discover** – Confirm `run_full_annotation_pipeline` is exposed by the active MCP catalog and inspect its current `inputSchema`.
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

- [ ] Live catalog confirms `run_full_annotation_pipeline` is currently exposed.
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
