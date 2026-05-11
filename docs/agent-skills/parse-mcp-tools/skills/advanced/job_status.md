---
name: parse-mcp-tool-job-status
description: "Use PARSE MCP tool `job_status`: Read the generic status of any PARSE background job by jobId. Returns type, status, progress, message, error, result, timestamps, and logCount."
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

# PARSE MCP Tool Skill — `job_status`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `job_status` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `job_status`
- **Skill name:** `parse-mcp-tool-job-status`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `jobId`
- **`additionalProperties`:** `False`
- **Catalog description:** Read the generic status of any PARSE background job by jobId. Returns type, status, progress, message, error, result, timestamps, and logCount.

### Parameters

- `jobId` (type=string; minLength=1; maxLength=128)

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- None advertised by the catalog.

### Postconditions advertised by catalog

- None advertised by the catalog.

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
curl "$PARSE_BASE_URL/api/mcp/tools/job_status?mode=active"
```

## Workflow

1. **Discover** – Confirm `job_status` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
- For job-backed workflows, record the returned `jobId` and poll until a terminal status before claiming completion.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Example API call/response

Successful HTTP MCP call for a known job UUID:

```bash
curl -s -X POST "$PARSE_BASE_URL/api/mcp/tools/job_status?mode=active" \
  -H 'Content-Type: application/json' \
  --data '{"jobId":"550e8400-e29b-41d4-a716-446655440000"}'
```

Representative response:

```json
{
  "tool": "job_status",
  "ok": true,
  "result": {
    "readOnly": true,
    "jobId": "550e8400-e29b-41d4-a716-446655440000",
    "type": "compute:forced_align",
    "status": "running",
    "progress": 42.0,
    "message": "Aligning Tier 1 word windows",
    "error": null,
    "errorCode": null,
    "result": null,
    "createdAt": "2026-05-10T20:15:00Z",
    "updatedAt": "2026-05-10T20:15:08Z",
    "completedAt": null,
    "meta": {
      "speaker": "Fail02",
      "computeType": "forced_align"
    },
    "locks": {
      "active": true,
      "resources": [
        {"kind": "speaker", "id": "Fail02"}
      ],
      "ttl_seconds": 600
    },
    "logCount": 3
  }
}
```

For unknown IDs, the tool returns `status: "not_found"`; do not retry blindly—recover a current ID with `jobs_list` or `jobs_list_active`.

## Quality checklist

- [ ] Live catalog confirms `job_status` is currently exposed.
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
