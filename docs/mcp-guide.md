# MCP & External API Guide

This guide is the narrative overview of PARSE's machine-facing surfaces. For the raw schema/auth reference, see [MCP Schema](mcp-schema.md). For the full endpoint inventory, examples, and OpenAPI details, see [API Reference](api-reference.md) and [Getting Started with External Agents](getting-started-external-agents.md).

## At a Glance

| Surface | Transport | Default entry point | Best for |
|---|---|---|---|
| HTTP API | HTTP | `http://127.0.0.1:8766` | Local scripts, service wrappers, custom orchestration |
| WebSocket job stream | WebSocket | `ws://127.0.0.1:8767/ws/jobs/{jobId}` | Live progress, logs, and segment streaming |
| HTTP MCP bridge | HTTP | `GET/POST /api/mcp/*` | Tool discovery and HTTP tool execution |
| stdio MCP adapter | stdio | `python python/adapters/mcp_adapter.py` | Claude Code, Cursor, Cline, Codex, Hermes, Windsurf |

## Tool Counts Verified Against Code

These counts were verified against `python/ai/chat_tools.py`, `python/ai/workflow_tools.py`, `python/external_api/catalog.py`, and the MCP adapter tests:

- **55** built-in `ParseChatTools`
- **55** default MCP task tools from `DEFAULT_MCP_TOOL_NAMES`
- **3** workflow macros from `DEFAULT_MCP_WORKFLOW_TOOL_NAMES`
- **59** total default adapter tools including the 3 workflow macros plus `mcp_get_exposure_mode`
- **59** total adapter tools when `config/mcp_config.json` or `mcp_config.json` sets `{ "expose_all_tools": true }`
- **36** legacy curated opt-out task tools from `LEGACY_CURATED_MCP_TOOL_NAMES`
- **40** total adapter tools when `config/mcp_config.json` or `mcp_config.json` explicitly sets `{ "expose_all_tools": false }`

The shipped default includes the BND-facing tools `compute_boundaries_start`, `compute_boundaries_status`, `retranscribe_with_boundaries_start`, and `retranscribe_with_boundaries_status`. The boundary-constrained STT compute path also accepts the alias `bnd_stt`, but `bnd_stt` is a compute alias rather than a separately registered MCP tool name.

New in the default write-capable surface: `clef_clear_data` wraps `POST /api/clef/clear`. It clears selected per-language `concepts` entries from `config/sil_contact_languages.json`, preserves `_meta` and language metadata, does not touch `parse-enrichments.json`, supports `dryRun=true` preview, and can optionally remove known provider caches under `config/cache/` (`wiktionary_*.json`, `wikidata_*.json`, `asjp_*.json`, `cldf_*`).

`run_full_annotation_pipeline` now supports concept-scoped reruns through `run_mode` (`full`, `concept-windows`, `edited-only`) and optional `concept_ids`. Non-full responses include `affected_concepts`; empty `edited-only` runs return a no-op instead of starting an empty job. `apply_timestamp_offset` responses include `shiftedConcepts` alongside `shiftedIntervals`.

## Surface 1: HTTP API

The PARSE backend serves a local HTTP API on `http://127.0.0.1:8766` by default.

Common endpoint families:

- `GET /api/config` — read workspace configuration
- `GET /api/annotations/{speaker}` and `POST /api/annotations/{speaker}` — read and write annotation payloads
- `POST /api/stt` and `POST /api/stt/status` — start and poll STT jobs
- `POST /api/compute/{computeType}` and `POST /api/compute/{computeType}/status` — run ORTH, IPA, contact-lexeme, and other compute jobs
- `GET /api/export/lingpy` and `GET /api/export/nexus` — download export artifacts
- `GET /api/jobs`, `GET /api/jobs/{jobId}`, and `GET /api/jobs/{jobId}/logs` — inspect generic job state and logs

OpenAPI and interactive docs are exposed on the same server:

- `GET /openapi.json`
- `GET /docs`
- `GET /redoc`

## Surface 2: WebSocket Job Streaming

PARSE also exposes live job streaming on `ws://127.0.0.1:8767/ws/jobs/{jobId}`. Override the default port with `PARSE_WS_PORT` when needed.

Current event types are:

- `job.snapshot`
- `job.progress`
- `job.log`
- `stt.segment`
- `job.complete`
- `job.error`

Streaming is additive rather than exclusive: the normal HTTP polling routes, callback hooks, and MCP observability tools still work alongside WebSocket clients.

## Surface 3: HTTP MCP Bridge

The HTTP MCP bridge exposes PARSE's MCP-visible tool surface over plain HTTP.

Core endpoints:

- `GET /api/mcp/exposure` — active exposure mode, config source, and tool counts
- `GET /api/mcp/tools` — active tool catalog with parameter schemas and PARSE safety metadata
- `GET /api/mcp/tools/{toolName}` — one tool schema
- `POST /api/mcp/tools/{toolName}` — execute one MCP-visible tool via HTTP

The `mode` query parameter accepts:

- `active` — obey `config/mcp_config.json` or the legacy root-level `mcp_config.json`
- `default` — expose the shipped default 59-tool surface
- `all` — expose the full tool surface (currently also 59 tools unless a future all-only surface diverges)

Each listed tool includes standard MCP schema fields plus `meta.x-parse` safety metadata such as `mutability`, `supports_dry_run`, `dry_run_parameter`, `preconditions`, and `postconditions`.

Recommended HTTP MCP flow:

1. Read `GET /api/mcp/exposure`.
2. Discover tools from `GET /api/mcp/tools`.
3. Inspect `meta.x-parse.preconditions` and `supports_dry_run`.
4. Prefer `dryRun=true` for mutating tools when available.
5. Execute with `POST /api/mcp/tools/{toolName}`.

## Surface 4: stdio MCP Adapter

The recommended external-agent entry point is the stdio adapter at `python/adapters/mcp_adapter.py`.

Start it from the repo root:

```bash
python python/adapters/mcp_adapter.py
```

Useful variants:

```bash
python python/adapters/mcp_adapter.py --project-root /path/to/project
python python/adapters/mcp_adapter.py --verbose
```

The adapter does not add a separate network protocol. It launches as a local process and relies on PARSE's existing environment conventions, especially:

- `PARSE_PROJECT_ROOT`
- `PARSE_EXTERNAL_READ_ROOTS`
- `PARSE_CHAT_MEMORY_PATH`
- `PARSE_API_PORT`
- `PARSE_PORT`

Use the shipped default 59-tool surface for most agent sessions. Set `config/mcp_config.json` → `{ "expose_all_tools": false }` only when you intentionally need the legacy curated opt-out surface.

## Authentication Model

PARSE's local HTTP API is **not bearer-protected** today. It is designed for local workstation use on `127.0.0.1:8766` / `localhost:8766` with permissive local automation rather than internet-facing deployment.

Provider credentials are managed separately through the auth endpoints:

- `GET /api/auth/status`
- `POST /api/auth/key`
- `POST /api/auth/start`
- `POST /api/auth/poll`
- `POST /api/auth/logout`

Supported auth paths currently include direct API-key storage for xAI/OpenAI-style providers and the OpenAI device/OAuth flow. Credentials are stored locally in `config/auth_tokens.json` and mirrored into the live process environment when needed. The stdio adapter does not add a second auth layer beyond local process access and environment scoping.

## Python Package: `parse-mcp`

PARSE also ships a publishable Python package scaffold under [`../python/packages/parse_mcp/`](../python/packages/parse_mcp/README.md).

Install options:

```bash
pip install parse-mcp
pip install 'parse-mcp[langchain]'
pip install 'parse-mcp[llamaindex]'
pip install 'parse-mcp[crewai]'
pip install 'parse-mcp[all]'
```

Basic usage:

```python
from parse_mcp import ParseMcpClient

client = ParseMcpClient(base_url="http://127.0.0.1:8766")
for tool in client.list_tools():
    print(tool.name, tool.family)

result = client.call_tool("project_context_read", {"include": ["project", "source_index"]})
print(result)
```

The package also provides ready-to-use wrappers for LangChain, LlamaIndex, and CrewAI.

## Related Docs

- [Getting Started with External Agents](getting-started-external-agents.md)
- [API Reference](api-reference.md)
- [MCP Schema](mcp-schema.md)
- [parse-mcp package README](../python/packages/parse_mcp/README.md)
