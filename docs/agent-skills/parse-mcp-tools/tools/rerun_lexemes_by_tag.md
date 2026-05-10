---
name: parse-mcp-tool-rerun-lexemes-by-tag
description: "Use PARSE MCP tool `rerun_lexemes_by_tag`: Run ORTH and/or IPA per concept that matches the tag query, returning the rerun text per (speaker, conceptId, field). Synchronous — jobId is always null. Per-concept failures populate results[i].statusCode and do not abort the batch. ANY = the union: a concept is included if it carries at least one of the selected tags. Use for broad discovery and batching. ALL = the intersection: a concept is included only if it carries every selected tag. Use for precise filtering. Refuses ambiguous tag labels in any mode (409) and refuses match='all' if any label is unknown OR ambiguous (400) — surface those to the user instead of running GPU on the wrong concept set."
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

# PARSE MCP Tool Skill — `rerun_lexemes_by_tag`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `rerun_lexemes_by_tag` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.
>
> Contract distinction: this page describes the MCP/chat tool wrapper, whose catalog snapshot is synchronous and returns `jobId: null`. The HTTP endpoint `POST /api/lexemes/rerun-by-tag` is intentionally different for new UI/API callers: it defaults to a tracked compute job and returns `202 + jobId` unless `async=false` is set for deprecated synchronous compatibility.

## Tool contract snapshot

- **Tool name:** `rerun_lexemes_by_tag`
- **Skill name:** `parse-mcp-tool-rerun-lexemes-by-tag`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `speakers`, `tagLabels`, `field`
- **`additionalProperties`:** `False`
- **Catalog description:** Run ORTH and/or IPA per concept that matches the tag query, returning the rerun text per (speaker, conceptId, field). Synchronous — jobId is always null. Per-concept failures populate results[i].statusCode and do not abort the batch. ANY = the union: a concept is included if it carries at least one of the selected tags. Use for broad discovery and batching. ALL = the intersection: a concept is included only if it carries every selected tag. Use for precise filtering. Refuses ambiguous tag labels in any mode (409) and refuses match='all' if any label is unknown OR ambiguous (400) — surface those to the user instead of running GPU on the wrong concept set.

### Parameters

- `speakers` (type=oneOf)
- `tagLabels` (type=array)
- `match` (type=string; default="any"; enum=`any`, `all`)
- `field` (type=string; enum=`ipa`, `ortho`, `both`)
- `pad` (type=number; default=0.2; enum=`0.0`, `0.2`, `0.5`)

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- None advertised by the catalog.

### Postconditions advertised by catalog

- The tool ran ORTH/IPA transcription synchronously over matched concept windows. It acquires per-speaker lock files under .parse-locks/ and consumes GPU time, but does not persist the rerun output to annotations. (`project_state`, `recommended`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/rerun_lexemes_by_tag?mode=active"
```

## Workflow

1. **Discover** – Confirm `rerun_lexemes_by_tag` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
- For job-backed workflows, record the returned `jobId` and poll until a terminal status before claiming completion.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Worked example

Call the HTTP MCP bridge with the same argument object an MCP adapter would pass to `rerun_lexemes_by_tag`:

```bash
curl -sS -X POST "$PARSE_BASE_URL/api/mcp/tools/rerun_lexemes_by_tag?mode=active" \
  -H "Content-Type: application/json" \
  --data '{
    "speakers": ["Speaker01", "Speaker02"],
    "tagLabels": ["weather"],
    "match": "any",
    "field": "both",
    "pad": 0.2
  }'
```

Equivalent MCP arguments:

```json
{
  "speakers": ["Speaker01", "Speaker02"],
  "tagLabels": ["weather"],
  "match": "any",
  "field": "both",
  "pad": 0.2
}
```

Typical synchronous success shape; `jobId` stays `null` and each ORTH/IPA cell is reported independently:

```json
{
  "tool": "rerun_lexemes_by_tag",
  "ok": true,
  "result": {
    "ok": true,
    "jobId": null,
    "resolved": {
      "totalConcepts": 2,
      "perSpeaker": {
        "Speaker01": {
          "conceptCount": 1,
          "concepts": [
            {
              "conceptId": "12",
              "name": "rain",
              "start": 10.25,
              "end": 11.1,
              "tags": ["weather"]
            }
          ]
        }
      },
      "unknownTags": [],
      "ambiguousTags": {}
    },
    "total": 2,
    "results": [
      {
        "speaker": "Speaker01",
        "conceptId": "12",
        "field": "ortho",
        "status": "ok",
        "text": "baran"
      },
      {
        "speaker": "Speaker01",
        "conceptId": "12",
        "field": "ipa",
        "status": "ok",
        "text": "baɾan"
      }
    ],
    "mode": "read-only",
    "readOnly": true,
    "previewOnly": true
  }
}
```

## Quality checklist

- [ ] Live catalog confirms `rerun_lexemes_by_tag` is currently exposed.
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
