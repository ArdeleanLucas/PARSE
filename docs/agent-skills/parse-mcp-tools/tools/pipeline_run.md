---
name: parse-mcp-tool-pipeline-run
description: "Use PARSE MCP tool `pipeline_run`: Kick off a transcription pipeline for ONE speaker — the same ``full_pipeline`` compute the UI uses. Supports any subset of ``normalize / stt / ortho / ipa`` in canonical order. Setting ``steps: ['ortho']`` with ``overwrites: {ortho: true}`` runs the configured ORTH model full-file against this speaker's working WAV and overwrites the ortho tier. Returns a jobId; poll via ``compute_status`` (compute_type=\"full_pipeline\") until ``status=complete``. Steps run step-resilient: a failing STT will not abort ORTH/IPA for the same speaker."
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

# PARSE MCP Tool Skill — `pipeline_run`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `pipeline_run` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `pipeline_run`
- **Skill name:** `parse-mcp-tool-pipeline-run`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `speaker`, `steps`
- **`additionalProperties`:** `False`
- **Catalog description:** Kick off a transcription pipeline for ONE speaker — the same ``full_pipeline`` compute the UI uses. Supports any subset of ``normalize / stt / ortho / ipa`` in canonical order. Setting ``steps: ['ortho']`` with ``overwrites: {ortho: true}`` runs the configured ORTH model full-file against this speaker's working WAV and overwrites the ortho tier. Returns a jobId; poll via ``compute_status`` (compute_type="full_pipeline") until ``status=complete``. Steps run step-resilient: a failing STT will not abort ORTH/IPA for the same speaker.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200) — Speaker ID whose pipeline should run.
- `steps` (type=array) — Ordered pipeline subset to execute for this speaker.
- `overwrites` (type=object) — Per-step overwrite flags. Steps flagged false will skip when their tier / cache is already populated; flagged true will replace the existing data.
- `language` (type=string; minLength=1; maxLength=32) — Optional language override forwarded to STT + ORTH (the configured project model). Empty / omitted = auto-detect for STT, the project default for ORTH.
- `run_mode` (type=string; default="full"; enum=`full`, `concept-windows`, `edited-only`) — Pipeline scope: full-file behavior, all concept windows, or manually adjusted concept windows only.
- `concept_ids` (type=array) — Optional exact concept-id filter used when run_mode is concept-windows or edited-only.
- `dryRun` (type=boolean) — If true, preview the planned compute payload without starting a background job.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The target speaker must exist in the current project and have the files needed for the requested steps. (`project_state`, `required`)

### Postconditions advertised by catalog

- When dryRun=false, a full_pipeline background job is created and can be polled via compute_status. (`job_state`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/pipeline_run?mode=active"
```

## Workflow

1. **Discover** – Confirm `pipeline_run` is exposed by the active MCP catalog and inspect its current `inputSchema`.
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

- [ ] Live catalog confirms `pipeline_run` is currently exposed.
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
