# PARSE — Phonetic Analysis & Review Source Explorer

> **Rebuild repo note (2026-04-25):** this repository is the isolated refactor/rebuild lane. The live/oracle repo remains [`ArdeleanLucas/PARSE`](https://github.com/ArdeleanLucas/PARSE). Refactor PRs should land here first; only controlled syncs or reverts should touch the live repo.

**Browser-based dual-mode workstation for linguistic fieldwork.**
Annotate per-speaker recordings with tiered IPA/orthography, then compare across speakers for cognate adjudication, borrowing detection, and export-ready historical-linguistic datasets.

<!-- TODO: Add a hero GIF here showing the unified React shell: Annotate waveform + tiers, Compare concept matrix + CLEF panel, and the AI chat dock. A wide GitHub-friendly GIF or screenshot strip would work well. -->
<!-- TODO: Add 2-3 static screenshots below the hero once the current UI settles: Annotate mode, Compare mode, and Lexeme Search / CLEF panels. -->

> **Status**: Active development. Thesis-critical features are landing frequently, interfaces and file contracts are still evolving, and PARSE should currently be treated as research software rather than beta software.

## ✨ What Makes PARSE Different

- **Dual-mode unified React shell** for annotation and comparison in one workspace
- **Fieldwork-first design** for long recordings, uneven metadata, and iterative review
- **AI-native workflow surface** with a built-in chat assistant powered by **50 PARSE-specific tools**
- **Full MCP server mode** exposing a curated **32-tool task surface** by default (**36** adapter tools including workflow macros + `mcp_get_exposure_mode`)
- **CLEF — Contact Lexeme Explorer Feature** for borrowing adjudication via a 10-provider contact-language lookup stack
- **Lexical Anchor Alignment System** for locating repeated lexical items across long recordings and across speakers
- **Export pipeline** for LingPy TSV and NEXUS outputs used in downstream comparative workflows

## 🚀 Quick Start

```bash
git clone https://github.com/TarahAssistant/PARSE-rebuild.git
cd PARSE-rebuild
npm install
./scripts/parse-run.sh
```

On a fresh clone, you will usually also want to:

- copy `config/ai_config.example.json` to `config/ai_config.json`
- review your local model/provider settings before serious speech work
- prefer a standalone `PARSE_WORKSPACE_ROOT` for real fieldwork data rather than writing runtime artifacts into the git checkout

Open:

- **Annotate**: http://localhost:5173/
- **Compare**: http://localhost:5173/compare

For full requirements, workspace setup, GPU/model configuration, and troubleshooting, see [Getting Started](docs/getting-started.md).

## 🛠️ Core Concepts

### Annotate Mode (`/`)

**Annotate** is the per-speaker segmentation and transcription workstation.

It combines:

- **WaveSurfer 7** waveform review for long recordings
- **Four annotation tiers**: IPA, orthography, concept, and speaker
- **Stacked transcription lanes** for STT, IPA, ORTH, plus optional **Words (Tier 1)** and **Boundaries (Tier 2)** diagnostic lanes with synchronized horizontal scrolling and inline edit / split / merge / delete controls
- **Audio normalization**, **speaker-level STT**, **ORTH transcription**, and **acoustic IPA fill** jobs
- **Tier 2 forced alignment** with wav2vec2 for tighter word-level boundaries plus paired Tier 1/Tier 2 read-only overlays for spotting boundary drift
- **Per-speaker undo/redo** for annotation edits, including merge recovery and STT-tier migration
- **Draggable timestamp correction** and clip-bounded playback for manual review
- **Batch transcription** with preflight checks, per-step **Keep / Overwrite** scope controls, rerun-failed support, and report rows that preserve backend job ids when the UI loses `/api` connectivity mid-run
- **Timestamp-offset detection/apply workflows** for constant CSV↔audio misalignment, now with async progress, crash-log surfacing, and protection for manually adjusted / anchored lexemes
- **Search & anchor lexeme** tooling built on the Lexical Anchor Alignment System
- **Shared tags** and the in-session **AI chat dock**

Annotate mode is where PARSE turns long, messy field recordings into time-aligned annotation data without forcing the user into disconnected tools.

### Compare Mode (`/compare`)

**Compare** is the cross-speaker review workspace.

It provides:

- A **concept × speaker matrix** for side-by-side lexical comparison
- Cognate controls for **accept**, **split**, **merge**, and **cycle**
- Per-row editing, speaker flags, and secondary actions for review work
- **Borrowing adjudication** aided by contact-language similarity evidence, dynamic primary-language similarity columns, and selectable reference forms
- **Enrichment overlays** for computed comparative metadata
- The **CLEF** panel for multi-source contact-language lookup, provenance-aware **Sources Report**, academic citation cards, and retryable populate workflows
- The same shared **tag system** used in Annotate mode
- Export to **LingPy-compatible TSV** and **NEXUS** for downstream phylogenetic analysis

Together, Annotate and Compare cover the full movement from speaker-specific audio review to cross-speaker historical analysis.

### AI Workflow Assistant

PARSE includes a built-in **domain-specific chat dock** powered by the configured LLM provider.

This assistant is not a generic chatbot. It operates through `ParseChatTools` and can inspect project state, guide annotation workflows, trigger jobs, help interpret comparative results, and support onboarding, export, and troubleshooting inside the same workstation.

Supported LLM backends currently include **xAI (Grok)** and **OpenAI**. Local speech and alignment work is handled separately through faster-whisper, Razhan, Silero VAD, and wav2vec2.

### MCP & External API

PARSE exposes four machine-facing integration surfaces:

1. **HTTP API** on `http://localhost:8766`
2. **WebSocket job streaming** on `ws://localhost:8767/ws/jobs/{jobId}` (override with `PARSE_WS_PORT`)
3. **HTTP MCP bridge** on the same server for schema discovery + tool execution
4. **stdio MCP adapter** through `python/adapters/mcp_adapter.py` (thin entrypoint; concrete adapter modules live under `python/adapters/mcp/`)

That means external agent clients such as Claude Code, Cursor, Cline, Hermes, Windsurf, Codex, or other MCP-capable tools can call a curated subset of PARSE functions programmatically, without going through the browser UI.

Current counts:
- **50** built-in `ParseChatTools`
- **3** workflow macros in `python/ai/workflow_tools.py`
- **32** default MCP task tools
- **36** total default MCP adapter tools including read-only `mcp_get_exposure_mode`
- **54** total MCP adapter tools with `config/mcp_config.json` → `{ "expose_all_tools": true }`

#### Generic job observability

- `GET /api/jobs` — list recent jobs with status / progress / type filters
- `GET /api/jobs/{jobId}` — read one generic job snapshot, including `errorCode`, `logCount`, and lock metadata
- `GET /api/jobs/{jobId}/logs` — read structured per-job logs (and crash-log tails when present)

These endpoints back the in-app progress UI, the MCP observability tools, and callback-driven external automation.

#### WebSocket job streaming

- `ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}`
- current v1 event types: `job.snapshot`, `job.progress`, `job.log`, `stt.segment`, `job.complete`, `job.error`

Streaming is additive: HTTP polling, callbacks, and MCP observability still work exactly as before.

#### OpenAPI and interactive docs

- `GET /openapi.json` — full OpenAPI 3.1 spec
- `GET /docs` — Swagger UI
- `GET /redoc` — ReDoc

#### HTTP MCP bridge

- `GET /api/mcp/exposure`
- `GET /api/mcp/tools`
- `GET /api/mcp/tools/{toolName}`
- `POST /api/mcp/tools/{toolName}`

These endpoints expose the MCP schema, strict parameter JSON schemas, and PARSE-specific safety metadata (`meta.x-parse`) over plain HTTP.

#### Authentication model

- The local PARSE HTTP server is **not bearer-protected**; it is intended for local workstation use.
- Provider credentials are managed separately through `/api/auth/*` and stored locally in `config/auth_tokens.json`.
- Supported auth methods currently include:
  - direct API keys via `POST /api/auth/key`
  - OpenAI device/OAuth flow via `POST /api/auth/start` + `POST /api/auth/poll`

#### Python package

Task 5 also adds the official publishable package scaffold:

- `python/packages/parse_mcp/`
- package name: **`parse-mcp`**

It provides:
- schema discovery from a running PARSE server
- HTTP tool execution against the MCP bridge
- framework wrappers for:
  - LangChain
  - LlamaIndex
  - CrewAI

## 📚 Documentation

- [Getting Started](docs/getting-started.md) — installation, launch paths, requirements, environment variables, `ai_config.json`, GPU notes, and troubleshooting
- [Getting Started with External Agents](docs/getting-started-external-agents.md) — MCP stdio setup, HTTP MCP bridge / `parse-mcp` entry points, environment conventions, and agent-facing examples
- [User Guide](docs/user-guide.md) — detailed Annotate/Compare workflows, CLEF usage, Lexical Anchor Alignment, and workspace hydration
- [AI Integration](docs/ai-integration.md) — providers, models, configuration, the 50-tool chat surface, and workflow macros
- [API Reference](docs/api-reference.md) — HTTP endpoints, generic job observability, OpenAPI docs, MCP bridge routes, examples, and the current MCP task surface
- [Architecture](docs/architecture.md) — system design, data model, and runtime responsibilities
- [Post-decomp File Map](docs/architecture/post-decomp-file-map.md) — canonical "where does code live now?" reference for the split backend/frontend modules
- [Developer Guide](docs/developer-guide.md) — local development flow, extension points, and contributor rules after the module splits
- [Research Context](docs/research-context.md) — thesis background, citation guidance, and research-software framing

If you are new to PARSE, start with **[Getting Started](docs/getting-started.md)** and then move to the **[User Guide](docs/user-guide.md)**.

## Research Workflow in One Pass

PARSE is designed around a real fieldwork sequence rather than a toy demo sequence:

1. **Load or import one speaker** into the active workspace
2. **Normalize audio** and inspect the waveform
3. **Run STT / ORTH / IPA support jobs** to seed time-aligned review
4. **Correct timestamps and confirm segments** in Annotate mode
5. **Search and anchor difficult lexemes** across long recordings
6. **Compare the concept set across speakers** in the matrix view
7. **Use CLEF evidence** when a borrowing analysis needs external lexical context — the first time you run **Borrowing detection (CLEF)** from the Compute panel, PARSE opens a guided setup modal where you pick 1–2 primary contact languages (English + Spanish by default) and optionally auto-populate lexeme forms from the provider stack. The config lives in `config/sil_contact_languages.json`; extend the language picker with `config/sil_catalog_extra.json`. Each language now also carries an ISO 15924 `script` hint so bare Reference Forms route deterministically between IPA-like Latin text and non-Latin script text. If your workspace was populated before the 2026-04-25 exact-match fix for `lingpy_wordlist`, rerun CLEF populate with overwrite so any previously misbucketed doculect forms are replaced.
8. **Export LingPy TSV or NEXUS** for downstream comparative and phylogenetic analysis

The guiding principle is simple: timestamps are central, human review stays explicit, and automation should make linguistic judgment faster rather than opaque.

## Core Runtime Notes

A few practical details matter up front:

- The active frontend is **React + Vite** in `src/`
- `src/api/client.ts` is now a **barrel**; concrete request helpers live under `src/api/contracts/`
- `src/stores/annotationStore.ts` is now a **barrel**; concrete annotation-store slices/helpers live under `src/stores/annotation/`
- The Python backend in `python/server.py` is now a **thin orchestrator**; most HTTP route logic lives under `python/server_routes/`
- MCP stdio entrypoint logic starts from `python/adapters/mcp_adapter.py`, with concrete adapter modules under `python/adapters/mcp/`
- Chat tool registration starts from `python/ai/chat_tools.py`, with concrete tool logic split across `python/ai/tools/` and `python/ai/chat_tools/`
- Provider routing starts from `python/ai/provider.py`, with concrete providers under `python/ai/providers/`
- The preferred development URLs are:
  - `http://localhost:5173/`
  - `http://localhost:5173/compare`
- After `npm run build`, the Python server can serve the built UI at:
  - `http://localhost:8766/`
  - `http://localhost:8766/compare`
- `config/ai_config.json` is machine-local and gitignored; start from `config/ai_config.example.json`
- For real fieldwork usage, PARSE is intended to run against a **workspace root outside the git checkout**
- `docs/architecture/post-decomp-file-map.md` is the canonical current-layout reference when older docs mention pre-split file paths

Those details are expanded in [Getting Started](docs/getting-started.md), [Developer Guide](docs/developer-guide.md), and [Post-decomp File Map](docs/architecture/post-decomp-file-map.md).

## 🔬 Research & Citation

PARSE was developed for a **Southern Kurdish dialect phylogenetics thesis** at the **University of Bamberg**.

The working dataset and workflow are oriented toward:

- long elicitation recordings
- concept-based wordlists
- multiple speakers of closely related varieties
- cognate review and borrowing adjudication
- downstream comparative analysis in **LingPy**, **LexStat**, and **BEAST 2**

If you use PARSE in academic work, please cite it as **research software** and use the repository's [`CITATION.cff`](CITATION.cff) file or GitHub's **Cite this repository** UI.

Suggested citation:

> Ardelean, L. M. (2026). *PARSE: Phonetic Analysis & Review Source Explorer* [Computer software]. University of Bamberg. https://github.com/ArdeleanLucas/PARSE

See [Research Context](docs/research-context.md) for full citation guidance and research framing.

## License

MIT License
