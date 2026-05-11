---
name: parse-mcp-tool-compute-status
description: "Use PARSE MCP tool `compute_status`: Poll any compute job (full_pipeline, ortho, ipa, contact-lexemes, …) by jobId. Read-only. Returns the job snapshot with status, progress, message, and — for completed jobs — the full ``result`` payload. For pipeline jobs the result includes per-step status and summary counts so the agent can reason about success/skip/error cells."
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

# PARSE MCP Tool Skill — `compute_status`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `compute_status` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `compute_status`
- **Skill name:** `parse-mcp-tool-compute-status`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `jobId`
- **`additionalProperties`:** `False`
- **Catalog description:** Poll any compute job (full_pipeline, ortho, ipa, contact-lexemes, …) by jobId. Read-only. Returns the job snapshot with status, progress, message, and — for completed jobs — the full ``result`` payload. For pipeline jobs the result includes per-step status and summary counts so the agent can reason about success/skip/error cells.

### Parameters

- `jobId` (type=string; minLength=1; maxLength=128)
- `computeType` (type=string; minLength=1; maxLength=64) — Optional expected compute type (e.g. "full_pipeline"). If provided, the tool validates the job's type matches before returning the snapshot.

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- The caller must provide a valid jobId from a previous start call. (`input_shape`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/compute_status?mode=active"
```

## Workflow

1. **Discover** – Confirm `compute_status` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
- For job-backed workflows, record the returned `jobId` and poll until a terminal status before claiming completion.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Example request/response

Request a typed status check so accidentally polling the wrong job class fails visibly:

```json
{
  "jobId": "compute-<ID>",
  "computeType": "full_pipeline"
}
```

Representative completed response:

```json
{
  "readOnly": true,
  "jobId": "compute-<ID>",
  "type": "compute:full_pipeline",
  "status": "complete",
  "progress": 100.0,
  "message": "Compute complete",
  "error": null,
  "result": {
    "speaker": "<SPEAKER_ID>",
    "steps_run": ["ortho", "ipa"],
    "results": {
      "ortho": {"status": "ok", "filled": 128},
      "ipa": {"status": "ok", "filled": 129}
    },
    "summary": {"ok": 2, "skipped": 0, "error": 0}
  }
}
```

If the response is `status: "invalid_job_type"`, keep the job evidence but re-check the original start call before making any pipeline success claim.

## Quality checklist

- [ ] Live catalog confirms `compute_status` is currently exposed.
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
