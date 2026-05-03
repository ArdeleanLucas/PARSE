# Getting Started with External Agents

> Last updated: 2026-04-27
>
> This guide covers the external-agent interfaces that are currently shipped in the PARSE repository. The commands and tool counts below were cross-checked against `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`), `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`), `python/ai/workflow_tools.py`, `python/adapters/test_mcp_adapter.py`, and the launcher/config docs already in this repo.

PARSE can be used programmatically by external agents and automation without opening the browser UI. Today, the recommended path is the built-in **MCP stdio adapter**. For custom scripts and services that do not speak MCP, PARSE also exposes a local **HTTP API**.

## Overview: current external-agent entry points

| Interface | Best for | Transport | Current status |
|---|---|---|---|
| **MCP adapter** | Claude, Cursor, Windsurf, Codex, other MCP-capable agents | stdio | Recommended |
| **HTTP API** | Local scripts, service wrappers, custom orchestration | HTTP (`http://localhost:8766`) | Supported |

If you are deciding where to start, use **MCP first**. It exposes PARSE tools directly, including workflow macros such as `run_full_annotation_pipeline`, `prepare_compare_mode`, and `export_complete_lingpy_dataset`.

## Prerequisites

Before connecting an external agent, make sure the following are in place:

- **Python 3.10+** and the PARSE project dependencies are installed.
- The PARSE repo is available locally.
- The **PARSE API server** is running on the expected port when you want job-backed MCP tools to work reliably.
- If you plan to use the MCP adapter, install the MCP SDK:

```bash
pip install 'mcp[cli]'
```

For normal local development, start PARSE with the launcher from the repo root:

```bash
./scripts/parse-run.sh
```

That gives you the backend on `http://localhost:8766` and the Vite frontend on `http://localhost:5173`.

## 1. Recommended: use PARSE through the MCP adapter

### Step 1: start the adapter

From the repo root:

```bash
python python/adapters/mcp_adapter.py
```

Useful variants:

```bash
python python/adapters/mcp_adapter.py --project-root /path/to/project
python python/adapters/mcp_adapter.py --verbose
```

### Step 2: configure your MCP client

A minimal client config looks like this:

```json
{
  "mcpServers": {
    "parse": {
      "command": "python",
      "args": ["/absolute/path/to/parse/python/adapters/mcp_adapter.py"],
      "env": {
        "PARSE_PROJECT_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

### Environment-variable best practices

For real use, it is better to keep the MCP config small and push machine-local paths into PARSE's existing environment conventions.

Recommended variables:

- `PARSE_PROJECT_ROOT` — project root the adapter should operate on
- `PARSE_EXTERNAL_READ_ROOTS` — extra absolute read roots outside the workspace
- `PARSE_CHAT_MEMORY_PATH` — optional persistent markdown memory path for PARSE chat tooling
- `PARSE_API_PORT` — backend port if you are not using `8766`

A fuller example:

```json
{
  "mcpServers": {
    "parse": {
      "command": "python",
      "args": ["/absolute/path/to/parse/python/adapters/mcp_adapter.py"],
      "env": {
        "PARSE_PROJECT_ROOT": "/absolute/path/to/your/project",
        "PARSE_EXTERNAL_READ_ROOTS": "/mnt/c/Users/Lucas/Thesis",
        "PARSE_CHAT_MEMORY_PATH": "/absolute/path/to/parse-memory.md",
        "PARSE_API_PORT": "8766"
      }
    }
  }
}
```

If you do not want to duplicate those values in each MCP client config, PARSE also supports a gitignored repo-local `.parse-env` file. The standalone MCP adapter reads that file automatically and only fills variables that are not already set in the process environment.

Example `.parse-env`:

```bash
PARSE_EXTERNAL_READ_ROOTS=/mnt/c/Users/Lucas/Thesis
PARSE_CHAT_MEMORY_PATH=/absolute/path/to/parse-memory.md
PARSE_API_PORT=8766
```

### Step 3: understand the exposed tool surface

The adapter ships with the full safe PARSE tool surface by default and supports an explicit legacy opt-out:

| Mode | What you get |
|---|---|
| **Default** | 62 MCP tools total: 58 default `ParseChatTools` + 3 workflow macros + `mcp_get_exposure_mode` |
| **Legacy curated opt-out** | 42 MCP tools total: 38 curated `ParseChatTools` + 3 workflow macros + `mcp_get_exposure_mode` via explicit `config/mcp_config.json` → `{ "expose_all_tools": false }` |
| **Expose all** | 62 MCP tools total: all 58 `ParseChatTools`, all 3 workflow macros, plus `mcp_get_exposure_mode` |

The shipped default already exposes the full safe ParseChatTools surface. Create `config/mcp_config.json` (preferred) or root-level `mcp_config.json` only when you want to force a specific active mode:

- `config/mcp_config.json` (preferred), or
- `mcp_config.json` at the project root (legacy fallback)

with:

```json
{
  "expose_all_tools": true
}
```

### Step 4: give the agent practical tasks

Examples:

- “Run `run_full_annotation_pipeline` for speaker `Fail02` with `dryRun=true` first, then rerun only edited concepts with `run_mode="edited-only"` if the preview is clean.”
- “Prepare compare mode for concepts `1-25` across `Fail01`, `Mand01`, and `Qasr01`.”
- “List active jobs, then show logs for the stalled job.”
- “Run `compute_boundaries_start` for one speaker, then `retranscribe_with_boundaries_start` after `tiers.ortho_words` is ready.”
- “Export the complete LingPy dataset after refreshing contact lexeme references.”

## 2. Use the local HTTP API for custom automation

If your automation stack does not speak MCP, talk directly to the PARSE backend over HTTP.

### Base URL

```text
http://localhost:8766
```

### Common endpoint families

| Endpoint family | Purpose |
|---|---|
| `GET /api/config` | Read workspace configuration |
| `GET /api/annotations/{speaker}` | Read one speaker's annotation payload |
| `GET /api/pipeline/state/{speaker}` | Inspect pipeline coverage and readiness |
| `POST /api/stt` + `POST /api/stt/status` | Start and poll STT jobs |
| `POST /api/compute/{computeType}` + status routes | Start and monitor ORTH / IPA / full-pipeline / contact-lexeme jobs |
| `GET /api/jobs`, `GET /api/jobs/{jobId}`, `GET /api/jobs/{jobId}/logs` | Generic job observability |
| `GET /api/export/lingpy`, `GET /api/export/nexus` | Download export artifacts |

### Example: read pipeline state

```bash
curl http://localhost:8766/api/pipeline/state/Fail02
```

### Example: start STT

```bash
curl -X POST http://localhost:8766/api/stt \
  -H 'Content-Type: application/json' \
  -d '{
    "speaker": "Fail02",
    "source_wav": "audio/working/Fail02/Fail02.wav",
    "language": "ku"
  }'
```

### Example: inspect generic job logs

```bash
curl "http://localhost:8766/api/jobs/stt-abc123/logs?offset=0&limit=50"
```

### Python example: list jobs with structured metadata

```python
import requests

base_url = "http://127.0.0.1:8766"
response = requests.get(
    f"{base_url}/api/jobs",
    params={"statuses": "running,queued", "limit": 10},
    timeout=30,
)
response.raise_for_status()
payload = response.json()

for job in payload.get("jobs", []):
    print(
        job.get("jobId"),
        job.get("type"),
        job.get("status"),
        job.get("progress"),
        job.get("message"),
    )
```

### Python example: inspect the stdio adapter directly

For advanced local scripting, you can also instantiate the PARSE MCP server directly inside Python and inspect the registered tool surface without going through a GUI client:

```python
import asyncio
import sys
from pathlib import Path

repo_root = Path("/absolute/path/to/PARSE")
sys.path.insert(0, str(repo_root / "python"))

from adapters.mcp_adapter import create_mcp_server

server = create_mcp_server(str(repo_root))

a_sync_tools = asyncio.run(server.list_tools())
print(f"Registered MCP tools: {len(a_sync_tools)}")
print(sorted(tool.name for tool in a_sync_tools)[:10])
```

This is useful when you want to validate the active MCP exposure mode or build custom local harnesses around the stdio adapter implementation itself.

These examples are useful when you are wrapping PARSE inside your own service, validating MCP exposure locally, or building custom harnesses around the agent-facing interface.

## Safety and best practices

- **Start with MCP unless you have a strong reason not to.** The tool layer is safer and more discoverable than calling low-level endpoints ad hoc.
- **Use `dryRun=true` first** for mutating or job-starting tools whenever the schema supports it.
- **Prefer workflow macros** when they match the task. They encode safer orchestration than hand-chaining several lower-level tool calls.
- **Respect PARSE preconditions and metadata.** MCP tools expose machine-readable `meta["x-parse"]` safety metadata, including mutability, dry-run support, preconditions, and postconditions.
- **Onboarding/import remains one speaker at a time.** Do not turn speaker onboarding into a bulk-import workflow.
- **Use coverage-aware checks.** For pipeline decisions, prefer `full_coverage` instead of treating bare `done=true` as sufficient.

## Common Issues & Solutions

### The MCP client connects, but tools fail when they try to start or inspect jobs

Make sure the PARSE backend is running on the expected API port. The adapter proxies job-backed operations through the local HTTP server, which defaults to `http://127.0.0.1:8766` unless you override `PARSE_API_PORT` or `PARSE_PORT`.

### The adapter cannot see files outside the project root

Set `PARSE_EXTERNAL_READ_ROOTS` to one or more absolute paths. Without that, the adapter stays inside the stricter workspace sandbox. For persistent local setup, put the value in `.parse-env`.

### My MCP client config is getting cluttered with path-specific environment variables

Keep only the essentials in the client config and move the rest into repo-local `.parse-env`. The adapter already knows how to load it.

### I expected fewer or more tools than I see by default

Current PARSE defaults to the full safe 62-tool adapter surface: 58 `ParseChatTools`, 3 workflow macros, and `mcp_get_exposure_mode`. If you need the older smaller surface, set `{"expose_all_tools": false}` in `config/mcp_config.json`; that publishes the legacy 42-tool adapter surface.

The default set includes the BND-facing tools `compute_boundaries_start`, `compute_boundaries_status`, `retranscribe_with_boundaries_start`, and `retranscribe_with_boundaries_status`, plus write-capable `clef_clear_data`, `csv_only_reimport`, and `revert_csv_reimport` tools for dry-run-capable CLEF reset and Audition CSV reimport/revert workflows. The shorter name `bnd_stt` is only a compute-type alias for the HTTP/background-job path, not a separately registered MCP tool name.

### Can I use an official `parse_mcp` Python package or an HTTP MCP bridge?

Yes. Current `main` ships both:

- the **HTTP MCP bridge** on the local PARSE server (`/api/mcp/exposure`, `/api/mcp/tools`, `/api/mcp/tools/{toolName}`)
- the official **`parse-mcp`** Python package scaffold under `python/packages/parse_mcp/`

For most local agent setups, the **stdio MCP adapter** is still the simplest place to start. Use the HTTP bridge or `parse-mcp` when you need schema discovery / execution over HTTP or wrapper integration with LangChain, LlamaIndex, or CrewAI.

## What’s next

After you are up and running:

- inspect the default 62-tool MCP surface from your client; set `expose_all_tools=false` only when you intentionally need the legacy curated opt-out
- try the workflow macros first: `run_full_annotation_pipeline`, `prepare_compare_mode`, and `export_complete_lingpy_dataset`
- use `mcp_get_exposure_mode` to confirm which MCP surface the current project is publishing
- move from this guide into the API and AI docs below when you need full schema and tool-reference detail

## Further reading

- [API Reference](./api-reference.md)
- [AI Integration](./ai-integration.md)
- [Getting Started](./getting-started.md)
- [Developer Guide](./developer-guide.md)
- MCP adapter source: `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`)
- Workflow macros: `python/ai/workflow_tools.py`
- Tool metadata source of truth: `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`)

> [!NOTE]
> If this guide saves you time, star the repo and join the PARSE discussion around external-agent workflows, MCP ergonomics, and field-ready automation.