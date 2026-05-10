---
name: parse-mcp-tool-export-complete-lingpy-dataset
description: "Use PARSE MCP tool `export_complete_lingpy_dataset`: Export a complete PARSE phylogenetics bundle using the existing low-level export tools. Writes LingPy TSV and NEXUS under exports/lingpy/, and can optionally refresh contact lexeme references before export."
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

# PARSE MCP Tool Skill — `export_complete_lingpy_dataset`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `export_complete_lingpy_dataset` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `export_complete_lingpy_dataset`
- **Skill name:** `parse-mcp-tool-export-complete-lingpy-dataset`
- **Family:** `workflow`
- **Mutability:** `mutating`
- **Supports dry-run:** `Yes — `dryRun``
- **Required inputs:** None
- **`additionalProperties`:** `False`
- **Catalog description:** Export a complete PARSE phylogenetics bundle using the existing low-level export tools. Writes LingPy TSV and NEXUS under exports/lingpy/, and can optionally refresh contact lexeme references before export.

### Parameters

- `with_contact_lexemes` (type=boolean) — If true, run contact_lexeme_lookup before the export steps.
- `dryRun` (type=boolean) — Preview the export bundle and planned artifacts without writing files.

### Dry-run command and expected output

HTTP MCP dry-run call:

```bash
curl -s "$PARSE_BASE_URL/api/mcp/tools/export_complete_lingpy_dataset?mode=active" \
  -H 'Content-Type: application/json' \
  -d '{"with_contact_lexemes":false,"dryRun":true}' \
  | python3 -m json.tool
```

Representative MCP HTTP response shape:

```json
{
  "tool": "export_complete_lingpy_dataset",
  "ok": true,
  "result": {
    "dryRun": true,
    "readOnly": true,
    "previewOnly": true,
    "mode": "read-only",
    "with_contact_lexemes": false,
    "artifacts": {
      "lingpy_tsv": "exports/lingpy/wordlist.tsv",
      "nexus": "exports/lingpy/dataset.nex"
    },
    "stages": [
      {
        "stage": "lingpy_tsv",
        "tool": "export_lingpy_tsv",
        "status": "preview",
        "payload": {
          "readOnly": true,
          "previewOnly": true,
          "previewLines": "ID\tCONCEPT\tDOCULECT\tIPA\tCOGID\tTOKENS\tBORROWING",
          "totalLines": 129,
          "truncated": true,
          "rowCount": 128
        }
      },
      {
        "stage": "nexus",
        "tool": "export_nexus",
        "status": "preview",
        "payload": {
          "readOnly": true,
          "previewOnly": true,
          "preview": "#NEXUS\n\nBEGIN TAXA;",
          "truncated": false,
          "totalChars": 321
        }
      }
    ],
    "final_status": "preview",
    "exported_at": "2026-05-10T19:24:00Z"
  }
}
```

If `with_contact_lexemes` is true, expect an additional first stage for `contact_lexeme_lookup`; keep dry-run evidence before any live export write.

### MCP annotations

- `destructiveHint`: `True`
- `idempotentHint`: `False`
- `readOnlyHint`: `False`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)
- At least some annotated project data must exist before exporting LingPy artifacts. (`project_state`, `required`)

### Postconditions advertised by catalog

- When dryRun=false, the LingPy TSV and NEXUS outputs are written inside the project export directory. (`filesystem_write`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/export_complete_lingpy_dataset?mode=active"
```

## Workflow

1. **Discover** – Confirm `export_complete_lingpy_dataset` is exposed by the active MCP catalog and inspect its current `inputSchema`.
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

- [ ] Live catalog confirms `export_complete_lingpy_dataset` is currently exposed.
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
