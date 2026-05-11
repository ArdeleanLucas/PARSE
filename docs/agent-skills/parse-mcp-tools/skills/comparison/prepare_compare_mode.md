---
name: parse-mcp-tool-prepare-compare-mode
description: "Use PARSE MCP tool `prepare_compare_mode`: Prepare a compare-mode bundle for a concept range across multiple speakers. Loads the requested annotations, computes a fresh cognate preview, and derives cross-speaker match previews from inline segments built from the selected concept windows."
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

# PARSE MCP Tool Skill — `prepare_compare_mode`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `prepare_compare_mode` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `prepare_compare_mode`
- **Skill name:** `parse-mcp-tool-prepare-compare-mode`
- **Family:** `workflow`
- **Mutability:** `read_only`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `concept_range`, `speakers`
- **`additionalProperties`:** `False`
- **Catalog description:** Prepare a compare-mode bundle for a concept range across multiple speakers. Loads the requested annotations, computes a fresh cognate preview, and derives cross-speaker match previews from inline segments built from the selected concept windows.

### Parameters

- `concept_range` (type=unspecified) — Either a range string like `"1-25"`, a single ID like `"42"`, or an explicit concept ID list such as `["1", "2", "3"]`.
- `speakers` (type=array)
- `dryRun` (type=boolean) — Preview the resolved speaker + concept scope without computing the full compare bundle.

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The caller must provide a concept_range and at least one speaker. (`input_shape`, `required`)

### Postconditions advertised by catalog

- The tool returns a structured compare bundle for the selected concepts and speakers. (`project_state`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/prepare_compare_mode?mode=active"
```

## Workflow

1. **Discover** – Confirm `prepare_compare_mode` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
- For job-backed workflows, record the returned `jobId` and poll until a terminal status before claiming completion.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Worked example

Valid `concept_range` inputs include a numeric range string, a single numeric ID, or an explicit ID list. Prefer `dryRun: true` first to confirm the resolved scope:

```json
{
  "concept_range": "1-25",
  "speakers": ["Khan01", "Khan02"],
  "dryRun": true
}
```

Equivalent explicit-list form for the first three concepts:

```json
{
  "concept_range": ["1", "2", "3"],
  "speakers": ["Khan01", "Khan02"],
  "dryRun": true
}
```

Dry-run response shape:

```json
{
  "tool": "prepare_compare_mode",
  "ok": true,
  "result": {
    "readOnly": true,
    "previewOnly": true,
    "mode": "read-only",
    "dryRun": true,
    "concept_ids": ["1", "2", "3"],
    "speakers": ["Khan01", "Khan02"],
    "speaker_count": 2,
    "note": "Dry run only. No compare preview computations were executed."
  }
}
```

## Quality checklist

- [ ] Live catalog confirms `prepare_compare_mode` is currently exposed.
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
