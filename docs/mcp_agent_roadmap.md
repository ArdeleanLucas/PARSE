# MCP / Agent Integration Roadmap

Future improvements to make PARSE a first-class citizen in agent-driven workflows.

---

## 1. Expose all 47 ParseChatTools via MCP

**Currently:** 47 internal tools power the chat dock; only 29 are exposed to external agents.

**What to do:** Make the remaining ~18 tools available through the MCP server — priority: write/edit/pipeline tools.

**Why it matters:** Agents (Claude, Cursor, custom Grok agents) are artificially limited today. Full exposure unlocks autonomous end-to-end workflows:

```
STT → alignment → IPA → Compare mode → LingPy export
```

**Bonus:** Add an opt-in flag in `mcp_config.json`:

```json
{ "expose_all_tools": true }
```

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
