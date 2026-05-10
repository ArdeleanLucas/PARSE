---
name: parse-mcp-tool-import-tag-csv
description: "Use PARSE MCP tool `import_tag_csv`: Import a CSV file as a custom tag list. Matches CSV rows to project concept IDs by label (case-insensitive), numeric ID, or fuzzy match (edit distance <= 1). When dryRun=true returns a preview of matched/unmatched rows and asks for tag name. When dryRun=false and tagName is provided, creates the tag and writes parse-tags.json. Always use dryRun=true first, then dryRun=false after explicit user confirmation."
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

# PARSE MCP Tool Skill — `import_tag_csv`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `import_tag_csv` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `import_tag_csv`
- **Skill name:** `parse-mcp-tool-import-tag-csv`
- **Family:** `chat`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** `dryRun`
- **`additionalProperties`:** `False`
- **Catalog description:** Import a CSV file as a custom tag list. Matches CSV rows to project concept IDs by label (case-insensitive), numeric ID, or fuzzy match (edit distance <= 1). When dryRun=true returns a preview of matched/unmatched rows and asks for tag name. When dryRun=false and tagName is provided, creates the tag and writes parse-tags.json. Always use dryRun=true first, then dryRun=false after explicit user confirmation.

### Parameters

- `csvPath` (type=string; maxLength=512)
- `tagName` (type=string; minLength=1; maxLength=100)
- `color` (type=string)
- `labelColumn` (type=string; maxLength=64)
- `dryRun` (type=boolean)
- `matchAllVariants` (type=boolean; default=true)
- `propagateToSpeakers` (type=boolean; default=true)

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
curl "$PARSE_BASE_URL/api/mcp/tools/import_tag_csv?mode=active"
```

## Workflow

1. **Discover** – Confirm `import_tag_csv` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as mutating or job-starting. Use an isolated test project first when possible.
- Run the advertised dry-run/preview mode first, then apply only after the result is inspected and the user has confirmed the intended mutation.
- Before live apply, snapshot the project artifacts the tool may write, then verify with an independent read-back after execution.
- If the tool starts a background job, poll the corresponding status tool or `job_status` until terminal state before reporting success.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Dry-run example

Sample dry-run input JSON for a custom tag CSV:

```json
{
  "csvPath": "imports/tags/thesis-priority.csv",
  "labelColumn": "concept_en",
  "tagName": "Thesis priority",
  "color": "#4461d4",
  "dryRun": true,
  "matchAllVariants": true,
  "propagateToSpeakers": true
}
```

Expected output format:

```json
{
  "ok": true,
  "matchedCount": 2,
  "unmatchedCount": 1,
  "matched": [
    {
      "csvLabel": "rain",
      "conceptId": "12",
      "conceptIds": ["12"],
      "conceptLabel": "rain"
    },
    {
      "csvLabel": "ice",
      "conceptId": "34-a",
      "conceptIds": ["34-a", "34-b"],
      "conceptLabel": "ice (A)"
    }
  ],
  "unmatched": [
    {"csvLabel": "hail"}
  ],
  "matchedConceptCount": 3,
  "dryRun": true,
  "preview": true,
  "message": "Will create tag 'Thesis priority' with 3 concepts. Call again with dryRun=false to confirm."
}
```

If `tagName` is omitted, the dry-run result sets `needsTagName: true` and asks what the tag should be called; provide the name only after reviewing matched/unmatched rows.

## Quality checklist

- [ ] Live catalog confirms `import_tag_csv` is currently exposed.
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
