---
name: parse-mcp-tool-list-concepts-by-tag
description: "Use PARSE MCP tool `list_concepts_by_tag`: Resolve a tag query and return matched concepts per speaker without running any STT/IPA work. Useful as the dry-run preview before calling rerun_lexemes_by_tag. ANY = the union: a concept is included if it carries at least one of the selected tags. Use for broad discovery and batching. ALL = the intersection: a concept is included only if it carries every selected tag. Use for precise filtering."
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

# PARSE MCP Tool Skill — `list_concepts_by_tag`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `list_concepts_by_tag` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `list_concepts_by_tag`
- **Skill name:** `parse-mcp-tool-list-concepts-by-tag`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `speakers`, `tagLabels`
- **`additionalProperties`:** `False`
- **Catalog description:** Resolve a tag query and return matched concepts per speaker without running any STT/IPA work. Useful as the dry-run preview before calling rerun_lexemes_by_tag. ANY = the union: a concept is included if it carries at least one of the selected tags. Use for broad discovery and batching. ALL = the intersection: a concept is included only if it carries every selected tag. Use for precise filtering.

### Parameters

- `speakers` (type=oneOf)
- `tagLabels` (type=array)
- `match` (type=string; default="any"; enum=`any`, `all`)

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- None advertised by the catalog.

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
curl "$PARSE_BASE_URL/api/mcp/tools/list_concepts_by_tag?mode=active"
```

## Workflow

1. **Discover** – Confirm `list_concepts_by_tag` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Valid `speakers` input examples

The `speakers` field is a `oneOf`: either an explicit array of speaker IDs or the literal string `"all"`.

Explicit speaker subset:

```json
{
  "speakers": ["Khan01", "Khan02"],
  "tagLabels": ["weather"],
  "match": "any"
}
```

All currently registered speakers:

```json
{
  "speakers": "all",
  "tagLabels": ["weather", "confirmed"],
  "match": "all"
}
```

Representative response shape:

```json
{
  "tool": "list_concepts_by_tag",
  "ok": true,
  "result": {
    "readOnly": true,
    "ok": true,
    "totalConcepts": 1,
    "perSpeaker": {
      "Khan01": {
        "conceptCount": 1,
        "concepts": [
          {"conceptId": "17", "name": "rain", "start": 12.34, "end": 13.1, "tags": ["weather"]}
        ]
      },
      "Khan02": {"conceptCount": 0, "concepts": []}
    },
    "unknownTags": [],
    "ambiguousTags": {},
    "mode": "read-only",
    "previewOnly": true
  }
}
```

## Quality checklist

- [ ] Live catalog confirms `list_concepts_by_tag` is currently exposed.
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
