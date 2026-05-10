---
name: parse-mcp-tool-export-annotations-textgrid
description: "Use PARSE MCP tool `export_annotations_textgrid`: Export speaker annotations to Praat TextGrid format (.TextGrid). Without outputPath returns a TextGrid string preview (first 2000 chars); with outputPath writes inside the project."
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

# PARSE MCP Tool Skill — `export_annotations_textgrid`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `export_annotations_textgrid` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `export_annotations_textgrid`
- **Skill name:** `parse-mcp-tool-export-annotations-textgrid`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `speaker`
- **`additionalProperties`:** `False`
- **Catalog description:** Export speaker annotations to Praat TextGrid format (.TextGrid). Without outputPath returns a TextGrid string preview (first 2000 chars); with outputPath writes inside the project.

### Parameters

- `speaker` (type=string; minLength=1; maxLength=200) — Speaker ID whose annotations should be converted to TextGrid format.
- `outputPath` (type=string; minLength=1; maxLength=512) — Project-relative or absolute path inside project root (e.g. exports/speaker.TextGrid).
- `dryRun` (type=boolean) — Preview only — never writes.

### Dry-run preview example

Input:

```json
{
  "speaker": "<SPEAKER_ID>",
  "dryRun": true
}
```

Representative result payload:

```json
{
  "readOnly": true,
  "previewOnly": true,
  "preview": "File type = \"ooTextFile\"\nObject class = \"TextGrid\"\n\nxmin = 0\nxmax = 123.45\ntiers? <exists>",
  "truncated": false,
  "totalChars": 1842
}
```

The preview is capped at the first 2000 characters; use `outputPath` plus `dryRun: false` to write the full `.TextGrid` file after validating the speaker scope.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- The requested speaker must already have an annotation file to export. (`file_presence`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/export_annotations_textgrid?mode=active"
```

## Workflow

1. **Discover** – Confirm `export_annotations_textgrid` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Quality checklist

- [ ] Live catalog confirms `export_annotations_textgrid` is currently exposed.
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
