---
name: parse-mcp-tool-phonetic-rules-apply
description: "Use PARSE MCP tool `phonetic_rules_apply`: Apply the project phonetic rules to IPA forms. Three modes:\n  normalize — strip delimiters, lowercase, normalise whitespace\n  apply     — return all rule-generated variants of a form\n  equivalence — compare two forms; returns isEquivalent + similarity score\nUses project phonetic_rules.json unless custom rules are supplied."
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

# PARSE MCP Tool Skill — `phonetic_rules_apply`

Use this portable skill when calling, validating, reviewing, or documenting the PARSE MCP tool `phonetic_rules_apply` for any research project, speaker set, language, or corpus hosted in PARSE.

> Source of truth: generated from `python/external_api/catalog.py::build_mcp_http_catalog(..., mode="all")` on `2026-05-10T17:37:02Z`. Re-discover the live schema before execution because tool contracts can evolve.

## Tool contract snapshot

- **Tool name:** `phonetic_rules_apply`
- **Skill name:** `parse-mcp-tool-phonetic-rules-apply`
- **Family:** `chat`
- **Mutability:** `read_only`
- **Supports dry-run:** `No`
- **Required inputs:** `form`
- **`additionalProperties`:** `False`
- **Catalog description:** Apply the project phonetic rules to IPA forms. Three modes:
  normalize — strip delimiters, lowercase, normalise whitespace
  apply     — return all rule-generated variants of a form
  equivalence — compare two forms; returns isEquivalent + similarity score
Uses project phonetic_rules.json unless custom rules are supplied.

### Parameters

- `form` (type=string; minLength=1; maxLength=256) — Primary IPA form to operate on.
- `mode` (type=string; enum=`normalize`, `apply`, `equivalence`) — Operation mode (default: normalize).
- `form2` (type=string; minLength=1; maxLength=256) — Second form for equivalence mode.
- `rules` (type=array) — Optional inline rule list (same schema as phonetic_rules.json entries). Omit to use the project file.

### MCP annotations

- `destructiveHint`: `False`
- `idempotentHint`: `True`
- `readOnlyHint`: `True`

### Preconditions advertised by catalog

- The PARSE project root must be available and readable. (`project_state`, `required`)

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
curl "$PARSE_BASE_URL/api/mcp/tools/phonetic_rules_apply?mode=active"
```

## Workflow

1. **Discover** – Confirm `phonetic_rules_apply` is exposed by the active MCP catalog and inspect its current `inputSchema`.
2. **Prepare arguments** – Supply required inputs exactly as named above; keep optional bounds conservative unless the task requires a broad sweep.
3. **Respect corpus neutrality** – Treat speaker IDs, concept IDs, tags, CSV labels, paths, and audio names as project-specific data. Do not hard-code language names or local workstation paths.
4. **Apply safety policy**:
- Treat this tool as read-only, but still bound result sizes when the schema offers `limit`, `maxIntervals`, or preview-size parameters.
- It is suitable for reconnaissance, schema validation, reports, and preflight checks.
- If results refer to annotation files, prefer active `annotations/<Speaker>.parse.json` artifacts for any independent audit.
5. **Verify** – Check returned JSON for `ok`, `error`, nested result payloads, skipped rows, warnings, and job IDs. Verify mutations by reading the relevant project artifacts back through a separate read-only path.

## Worked examples

These examples use inline rules so the results are deterministic across projects. Omit `rules` to use the project's `phonetic_rules.json`. In wrapped HTTP/MCP responses, `result.mode` stays `read-only`; the requested operation is visible from the distinct result keys (`normalized`, `variants`, or `isEquivalent`/`similarityScore`).

Normalize strips IPA delimiters, lowercases, and normalizes whitespace:

```json
{
  "form": " /Yek/ ",
  "mode": "normalize"
}
```

```json
{
  "tool": "phonetic_rules_apply",
  "ok": true,
  "result": {
    "readOnly": true,
    "previewOnly": true,
    "mode": "read-only",
    "form": "/Yek/",
    "normalized": "yek"
  }
}
```

Apply returns the canonical rule-applied form in `variants`:

```json
{
  "form": "pa",
  "mode": "apply",
  "rules": [
    {
      "from": "p",
      "to": "b",
      "context": "onset",
      "bidirectional": false
    }
  ]
}
```

```json
{
  "tool": "phonetic_rules_apply",
  "ok": true,
  "result": {
    "readOnly": true,
    "previewOnly": true,
    "mode": "read-only",
    "form": "pa",
    "normalized": "pa",
    "variants": "ba"
  }
}
```

Equivalence compares two forms and returns a boolean plus rounded similarity score:

```json
{
  "form": "pa",
  "form2": "ba",
  "mode": "equivalence",
  "rules": [
    {
      "from": "p",
      "to": "b",
      "context": "onset",
      "bidirectional": false
    }
  ]
}
```

```json
{
  "tool": "phonetic_rules_apply",
  "ok": true,
  "result": {
    "readOnly": true,
    "previewOnly": true,
    "mode": "read-only",
    "form": "pa",
    "form2": "ba",
    "isEquivalent": true,
    "similarityScore": 1.0
  }
}
```

## Quality checklist

- [ ] Live catalog confirms `phonetic_rules_apply` is currently exposed.
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
