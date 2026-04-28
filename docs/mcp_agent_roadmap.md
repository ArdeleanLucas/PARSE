# MCP / Agent Integration Status

This document is now primarily a **status record**, not a speculative roadmap. The core MCP and external-agent work originally proposed here has been shipped on `main`; what remains is a short list of optional hardening and deployment extensions.

---

## Current state at a glance

PARSE now ships a full workstation-local external-agent surface:

- **54** in-app `ParseChatTools`
- **54** default MCP task tools
- **3** workflow macros
- **58** tools on the default adapter surface including `mcp_get_exposure_mode`
- **58** tools on the full adapter surface when `expose_all_tools=true`
- **40** tools on the legacy curated opt-out surface when `expose_all_tools=false` is configured explicitly
- **OpenAPI 3.1** docs at `GET /openapi.json`, `GET /docs`, and `GET /redoc`
- **HTTP MCP bridge** on the main PARSE server
- **stdio MCP adapter** for MCP-native clients
- **publishable `parse-mcp` package scaffold** for Python / framework integrations
- **generic job observability** over HTTP, MCP, and WebSocket streaming

In other words: PARSE is already usable as an agent-facing workstation API, not just an internal browser app.

---

## 1. Tool exposure via MCP

**Status:** ✅ Complete

**Shipped on `main`:**
- `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) exposes the shipped **55-tool** default task surface from `DEFAULT_MCP_TOOL_NAMES`.
- `python/ai/workflow_tools.py` adds **3** workflow macros on top of that base.
- `mcp_get_exposure_mode` is always available so clients can inspect the active exposure mode.
- `config/mcp_config.json` (or fallback root `mcp_config.json`) can opt into the legacy curated surface or explicitly force full exposure:

```json
{ "expose_all_tools": false }
```

or

```json
{ "expose_all_tools": true }
```

**Current totals:**
- default adapter surface: **58** tools total
- legacy curated opt-out surface: **40** tools total
- full adapter surface: **58** tools total

**Why this matters:**
PARSE no longer requires external agents to tunnel through the browser chat dock to reach core workstation actions.

---

## 2. Machine-readable tool contracts and safety metadata

**Status:** ✅ Complete

**Shipped on `main`:**
- MCP-visible tools publish strict JSON Schemas from `ChatToolSpec.parameters`.
- Tool metadata includes `meta["x-parse"]` safety annotations with:
  - `mutability`
  - `supports_dry_run`
  - `dry_run_parameter`
  - `preconditions`
  - `postconditions`
- Long-running starters are marked as `stateful_job`.
- Mutating and job-starting tools expose dry-run previews where supported.

**Why this matters:**
Agents can now inspect execution risk and workflow semantics programmatically instead of inferring them from prose.

---

## 3. Composite / workflow tools

**Status:** ✅ Complete

**Shipped on `main`:**
- `python/ai/workflow_tools.py` provides high-level macros with their own MCP-visible schemas and safety metadata.
- Current workflow macros:
  - `run_full_annotation_pipeline`
  - `prepare_compare_mode`
  - `export_complete_lingpy_dataset`
- These wrap existing low-level handlers rather than duplicating business logic.
- All three workflow tools support `dryRun` and publish machine-readable preconditions/postconditions.

**Why this matters:**
External agents can invoke meaningful workstation-level tasks directly instead of hand-assembling every low-level call sequence themselves.

---

## 4. Observability and job control

**Status:** ✅ Complete

**Shipped on `main`:**
- Generic HTTP job endpoints:
  - `GET /api/jobs`
  - `GET /api/jobs/{jobId}`
  - `GET /api/jobs/{jobId}/logs`
- Matching MCP tools:
  - `jobs_list`
  - `job_status`
  - `job_logs`
- Structured job payloads now include progress, `errorCode`, `logCount`, and lock metadata.
- Heavy job starters can emit callback payloads through `callbackUrl`.
- Speaker-scoped lock metadata helps prevent silent concurrent mutation.

**Why this matters:**
The same job can now be monitored coherently from the browser UI, HTTP automation, or an MCP client.

---

## 5. Standardized external HTTP surface

**Status:** ✅ Complete

**Shipped on `main`:**
- `GET /openapi.json` serves an **OpenAPI 3.1** document.
- `GET /docs` and `GET /redoc` expose interactive HTTP documentation.
- The PARSE server now includes an **HTTP MCP bridge**:
  - `GET /api/mcp/exposure`
  - `GET /api/mcp/tools`
  - `GET /api/mcp/tools/{toolName}`
  - `POST /api/mcp/tools/{toolName}`
- Shared schema/discovery helpers under `python/external_api/` keep HTTP and stdio MCP surfaces aligned.
- The repository now contains a publishable **`python/packages/parse_mcp/`** scaffold with:
  - `ParseMcpClient`
  - LangChain wrappers
  - LlamaIndex wrappers
  - CrewAI wrappers
- Agent-relevant non-MCP helper routes are also documented and shipped, including:
  - `GET/POST /api/clef/config`
  - `GET /api/clef/catalog`
  - `GET /api/clef/providers`
  - `GET /api/clef/sources-report`
  - `POST /api/clef/form-selections`

**Why this matters:**
PARSE now has a coherent external HTTP surface for both direct automation and MCP-backed wrappers.

---

## 6. Streaming job updates

**Status:** ✅ Complete

**Shipped on `main`:**
- `python/external_api/streaming.py` adds a WebSocket sidecar without replacing the existing custom HTTP server.
- The sidecar runs on `PARSE_WS_PORT` with default port `8767`.
- Subscription path:
  - `ws://<host>:<ws_port>/ws/jobs/{jobId}`
- Current v1 events:
  - `job.snapshot`
  - `job.progress`
  - `job.log`
  - `stt.segment`
  - `job.complete`
  - `job.error`
- Generic events are reusable across job types; `stt.segment` is the additive STT-specific packet.

**Why this matters:**
External agents no longer need to rely exclusively on polling for long-running job feedback.

---

## 7. What is actually still future work?

Most of the original roadmap has landed. The real remaining work is now narrower and mostly optional:

| Remaining idea | Why it could still matter |
|---|---|
| Built-in permission / sandbox scopes | Limit an agent to specific speakers, exports, or mutating operations |
| Remote or multi-user deployment mode | Support headless/cloud PARSE instances beyond a single trusted workstation |
| Richer webhook/event subscriptions | Push selected job/tool events into external orchestration systems without polling |
| Additional packaged clients/examples | Lower friction for framework-specific integrations beyond the current scaffold |

These are no longer prerequisites for PARSE agent integration; they are follow-on hardening and expansion work.

---

## Bottom line

The historical roadmap in this file is **largely complete**. If you are looking for the current external-agent surface, treat the following as the primary live references instead:

- `docs/mcp-schema.md`
- `docs/api-reference.md`
- `docs/getting-started-external-agents.md`
- `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`)
- `python/external_api/`
- `python/packages/parse_mcp/`
