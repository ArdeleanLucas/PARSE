# PARSE MCP tool skills for agents

This directory is a repo-owned, portable skill reference for PARSE MCP tools. It is meant for any agent or researcher using PARSE with any language, corpus, speaker inventory, or fieldwork project.

The skills are generic by design:

- no workstation-specific paths
- no project- or language-specific assumptions
- no credentials or local connection strings
- project roots and external data locations are expressed as placeholders such as `<PARSE_REPO>`, `<PROJECT_ROOT>`, and `$PARSE_EXTERNAL_READ_ROOTS`
- each tool page is generated from the live PARSE MCP catalog instead of hand-written memory

## Live catalog snapshot

Generated at `2026-05-10T17:37:02Z` from `python/external_api/catalog.py::build_mcp_http_catalog(project_root=<temporary_project>, mode="all")`.

| Surface | Count |
|---|---:|
| Parse chat/task tools | 60 |
| Workflow macros | 3 |
| Adapter tools | 1 |
| Full/default MCP surface | 64 |
| Legacy curated opt-out surface (`expose_all_tools=false`) | 44 |

`index.md` lists every generated tool skill and links to the per-tool pages under `skills/<bucket>/` (annotation, comparison, export, project, advanced).

## How agents should use these skills

1. Start with the relevant tool page from `skills/<bucket>/`.
2. Re-discover the live tool schema from the active PARSE instance before execution.
3. Use dry-run/preview first whenever the tool advertises it.
4. For mutating tools, snapshot relevant project artifacts and verify by read-back.
5. For job-backed tools, poll the returned `jobId` to terminal state before reporting success.
6. Keep speaker IDs, concept IDs, tags, CSV labels, and audio paths project-specific; do not encode language- or corpus-specific assumptions into reusable workflows.

## Portable MCP adapter invocation

```bash
cd <PARSE_REPO>
export PARSE_PROJECT_ROOT=<PROJECT_ROOT>
# Optional: colon-separated absolute roots for allowed external input files.
export PARSE_EXTERNAL_READ_ROOTS=<ABSOLUTE_READ_ROOT_1>[:<ABSOLUTE_READ_ROOT_2>]
PYTHONPATH=python python3 -m adapters.mcp_adapter --project-root "$PARSE_PROJECT_ROOT"
```

Use module form (`python3 -m adapters.mcp_adapter`) rather than launching `python/adapters/mcp_adapter.py` by file path, so the repo-local `python/adapters/mcp/` package does not shadow the installed MCP package.

## HTTP MCP bridge discovery

When the PARSE server is running, agents can inspect the same schema through the HTTP MCP bridge:

```bash
export PARSE_BASE_URL=http://127.0.0.1:8766
curl "$PARSE_BASE_URL/api/mcp/exposure?mode=active"
curl "$PARSE_BASE_URL/api/mcp/tools?mode=active"
curl "$PARSE_BASE_URL/api/mcp/tools/<toolName>?mode=active"
```

The HTTP bridge and stdio adapter share catalog metadata. If they disagree, treat that as an integration bug and verify against `python/external_api/catalog.py`.

## Regeneration check

From the PARSE repo root:

```bash
PYTHONPATH=python python3 - <<'PY'
from pathlib import Path
from external_api.catalog import build_mcp_http_catalog
catalog = build_mcp_http_catalog(project_root=Path('/tmp/parse-mcp-skill-check'), mode='all')
print(catalog['count'])
print('\\n'.join(tool['name'] for tool in catalog['tools']))
PY
```

The generated docs in this directory should match that tool list exactly.

## Related docs

- [MCP guide](../../mcp-guide.md)
- [MCP schema](../../mcp-schema.md)
- [External agents quickstart](../../getting-started-external-agents.md)
- [API reference](../../api-reference.md)
