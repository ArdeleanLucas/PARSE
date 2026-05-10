---
name: parse-mcp-tool-export-lingpy-tsv
description: "Use PARSE MCP tool `export_lingpy_tsv`: Export a LingPy-compatible wordlist TSV from enrichments + annotations for cognate analysis. Without outputPath returns first 20 lines; with outputPath writes inside the project."
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

# PARSE MCP Tool Skill — `export_lingpy_tsv`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `export_lingpy_tsv` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `export_lingpy_tsv`
- **Skill name:** `parse-mcp-tool-export-lingpy-tsv`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** None
- **`additionalProperties`:** `False`
- **Catalog description:** Export a LingPy-compatible wordlist TSV from enrichments + annotations for cognate analysis. Without outputPath returns first 20 lines; with outputPath writes inside the project.

### Parameters

- `outputPath` (type=string; minLength=1; maxLength=512) — Project-relative or absolute path inside project root.
- `dryRun` (type=boolean) — Preview only — never writes.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- parse-enrichments.json and the annotation inventory must contain enough data to build a LingPy export. (`project_state`, `required`)

### Postconditions advertised by catalog

- When dryRun=false and outputPath is provided, the requested export file is written inside the project. (`filesystem_write`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/export_lingpy_tsv?mode=active"
```

## Workflow

1. **Discover** – Confirm `export_lingpy_tsv` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Worked example

Use a project-relative `outputPath` such as `exports/lingpy_wordlist.tsv`; PARSE resolves it under `PARSE_PROJECT_ROOT` and creates the parent directory before writing.

```json
{
  "outputPath": "exports/lingpy_wordlist.tsv",
  "dryRun": false
}
```

Representative write response:

```json
{
  "success": true,
  "outputPath": "<PROJECT_ROOT>/exports/lingpy_wordlist.tsv",
  "rowCount": 128
}
```

For a no-write preview, omit `outputPath` or set `dryRun: true`; the result includes `previewLines`, `totalLines`, `truncated`, and `rowCount`.

## Quality checklist

- [ ] Live catalog confirms `export_lingpy_tsv` is currently exposed.
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
