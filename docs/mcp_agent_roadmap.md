# MCP / Agent Integration Roadmap

Future improvements to make PARSE a first-class citizen in agent-driven workflows.

---

## 1. Expose all 47 ParseChatTools via MCP

**Status:** ✅ Complete

**Shipped:**
- `python/adapters/mcp_adapter.py` still exposes the legacy **29 `ParseChatTools`** surface by default.
- Task 3 adds 3 workflow macros on top of that base, so the current default adapter surface is **33 tools total** including `mcp_get_exposure_mode`.
- Opt-in config at `config/mcp_config.json` (or fallback root `mcp_config.json`) enables the full **47-tool** `ParseChatTools` surface; with the 3 workflow macros and `mcp_get_exposure_mode`, the current full adapter surface is **51 tools total**:

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

**Status:** ✅ Complete

**Shipped:**
- Added `python/ai/workflow_tools.py` with a dedicated `WorkflowTools` class.
- New macros are exposed via MCP with their own `ChatToolSpec` metadata:
  - `run_full_annotation_pipeline(speaker_id, concept_list, dryRun=False)`
  - `prepare_compare_mode(concept_range, speakers, dryRun=False)`
  - `export_complete_lingpy_dataset(with_contact_lexemes=True, dryRun=False)`
- The macros orchestrate existing low-level tool handlers directly rather than duplicating business logic:
  - annotation workflow: `stt_start` → `stt_status` → `forced_align_start` → `forced_align_status` → `ipa_transcribe_acoustic_start` → `ipa_transcribe_acoustic_status`
  - compare prep: `speakers_list`, `annotation_read`, `cognate_compute_preview`, `cross_speaker_match_preview`
  - export bundle: `contact_lexeme_lookup`, `export_lingpy_tsv`, `export_nexus`
- Each macro publishes machine-readable preconditions/postconditions and supports `dryRun` where appropriate.
- MCP adapter now exposes the workflow macros in both default and full-exposure modes.

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
