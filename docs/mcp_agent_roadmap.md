# MCP / Agent Integration Roadmap

Future improvements to make PARSE a first-class citizen in agent-driven workflows.

---

## 1. Expose all 47 ParseChatTools via MCP

**Status:** ✅ Complete

**Shipped:**
- `python/adapters/mcp_adapter.py` still exposes the legacy **29 `ParseChatTools`** surface by default.
- MCP now also includes read-only `mcp_get_exposure_mode`, so the total adapter surface is **30 tools by default**.
- Opt-in config at `config/mcp_config.json` (or fallback root `mcp_config.json`) enables the full **47-tool** `ParseChatTools` surface, for **48 MCP tools total** including `mcp_get_exposure_mode`:

```json
{ "expose_all_tools": true }
```

**Notes:**
- Default behavior is unchanged for existing callers that rely on the legacy 29 PARSE tool wrappers.
- The internal chat dock still uses `ParseChatTools` directly; this task only changes MCP exposure.
- Newly exposed tools include the missing write/export/pipeline helpers such as normalize, enrichments, lexeme notes, exports, peaks, source-index validation, and transcript reformatting.
- `mcp_get_exposure_mode` lets external agents self-inspect whether the active MCP server is running in the default or full-exposure mode.

---

## 2. Richer, safer tool definitions

- Strict JSON schemas and detailed parameter descriptions for every tool (MCP supports this natively).
- Expose dry-run / preview mode on all mutating tools (many already have it internally).
- Add `preconditions` and `postconditions` fields so agents can reason safely:
  > "this tool requires a loaded project and at least one audio file"

---

## 3. High-level composite / workflow tools

Instead of chaining 47 low-level calls, give agents a handful of macro tools:

| Tool | Purpose |
|------|---------|
| `run_full_annotation_pipeline(speaker_id, concept_list)` | STT → alignment → IPA in one call |
| `prepare_compare_mode(concept_range, speakers)` | Load and diff a concept set across speakers |
| `export_complete_lingpy_dataset(with_contact_lexemes=True)` | Full phylogenetics export |

Macros are easier to discover, easier to prompt, and safer to execute.

---

## 4. Observability & control layer

Critical for long-running agent jobs:

- Expose job queue status, progress percentage, and live logs via MCP/HTTP.
- Add webhook / callback URL support so agents are notified when heavy jobs finish (e.g., batch STT on a 2-hour recording).
- Resource locking so a human and an agent can't mutate the same speaker concurrently.

---

## 5. Standardize the external API surface

- Generate and serve a full **OpenAPI 3.1 spec** for the HTTP API (port 8766).
- Publish official **LangChain / LlamaIndex / CrewAI** tool wrappers as a `parse-mcp` Python package.
- Document the MCP schema and authentication model clearly in the README.

---

## 6. Future / nice-to-have

| Idea | Value |
|------|-------|
| Streaming responses (WebSocket) | Agents get real-time waveform updates or partial results |
| Built-in sandbox / permission system | Scope an agent to a single speaker: `"agent can only edit speaker X"` |
| Remote / cloud mode | Run PARSE headless on a GPU server; agents connect via MCP over the internet |
