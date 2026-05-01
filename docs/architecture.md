# Architecture & Data Model

> Last updated: 2026-04-29
>
> This document summarizes the current PARSE system shape: the unified React shell, Python backend, hybrid data model, Lexical Anchor Alignment System, CLEF provider registry, and export flow.

PARSE is a research workstation rather than a single-purpose annotator. Its architecture is designed to keep per-speaker timing work, cross-speaker comparison, AI-assisted workflows, and export pipelines in one coherent system.

## System overview

```mermaid
flowchart LR
    Browser[React + Vite frontend\nAnnotate / Compare / Tags / AI Chat] --> Client[src/api/client.ts\nbarrel]
    Client --> ClientContracts[src/api/contracts/*\nconcrete request helpers]
    ClientContracts --> Server[python/server.py\nthin HTTP orchestrator]
    Server --> Routes[python/server_routes/*\nroute-domain modules]
    Routes --> Annotations[annotations/<Speaker>.json\nper-speaker annotation records]
    Routes --> Enrichments[parse-enrichments.json\ncomparative overlays + notes]
    Server --> ChatRegistry[python/ai/chat_tools.py\nregistry/orchestrator]
    ChatRegistry --> ChatModules[python/ai/tools/* +\npython/ai/chat_tools/*]
    Server --> Compare[python/compare/*\ncognates + CLEF providers]
    Server --> Providers[python/ai/provider.py\nbase provider surface]
    Providers --> ProviderModules[python/ai/providers/*\nconcrete providers]
    Server --> Stream[WebSocket sidecar\nPARSE_WS_PORT + /ws/jobs/{jobId}]
    Server --> External[OpenAPI 3.1 + HTTP MCP bridge\n/openapi.json + /api/mcp/*]
    ChatRegistry --> MCP[python/adapters/mcp_adapter.py\nthin stdio entrypoint]
    MCP --> MCPModules[python/adapters/mcp/*\ntransport + schema + dispatch]
    External --> PyPkg[python/packages/parse_mcp\nLangChain / LlamaIndex / CrewAI wrappers]
    Compare --> Exports[LingPy TSV + NEXUS]
```

## Unified dual-mode shell

The current frontend architecture is **React + Vite** with a unified shell hosted in `ParseUI.tsx`.

That shell brings together:

- **Annotate mode** for per-speaker segmentation and review
- **Compare mode** for cross-speaker comparative analysis
- the shared **tag system**
- the **action menu** and compute workflows
- the built-in **AI chat dock**

This is a major architectural choice: PARSE does not treat annotation, comparison, and workflow assistance as separate apps. The same project state is reused across modes.

### Current runtime routes

Preferred development routes:

- `http://localhost:5173/` — Annotate
- `http://localhost:5173/compare` — Compare

After `npm run build`, the Python backend can also serve the built frontend at:

- `http://localhost:8766/`
- `http://localhost:8766/compare`

## Frontend structure

The rebuild still presents a stable top-level shell, but several high-traffic files are now **barrels** or thin shells rather than the concrete implementation homes they used to be.

Key examples:

- `src/api/client.ts` — barrel only; concrete helpers live under `src/api/contracts/`
- `src/stores/annotationStore.ts` — barrel only; concrete slices/helpers live under `src/stores/annotation/`
- `src/components/compute/ClefConfigModal.tsx`, `ClefSourcesReportModal.tsx`, `ClefPopulateSummaryBanner.tsx` — barrels only; concrete UI modules live under `src/components/compute/clef/`
- `src/components/compare/BorrowingPanel.tsx`, `ConceptTable.tsx`, `LexemeDetail.tsx`, `CognateControls.tsx` — barrels only; concrete UI modules live under `src/components/compare/compare-panels/`
- `src/components/annotate/AnnotateView.tsx`, `AnnotateMode.tsx`, `AnnotationPanel.tsx`, `LexemeSearchPanel.tsx` — barrels only; concrete UI modules live under `src/components/annotate/annotate-views/`
- `src/hooks/useWaveSurfer.ts` and `src/hooks/useBatchPipelineJob.ts` — barrels only; concrete hook pieces live under `src/hooks/wave-surfer/` and `src/hooks/batch-pipeline/`

For the current file-by-file layout, use [Post-decomp File Map](./architecture/post-decomp-file-map.md).

## Backend design

The backend is centered on `python/server.py`, but that file is now deliberately a **thin orchestrator**.

Most concrete route behavior lives in `python/server_routes/`:

- `annotate.py`
- `compare.py`
- `jobs.py`
- `exports.py`
- `config.py`
- `clef.py`
- `chat.py`
- `media.py`

`python/server.py` is still responsible for:

- startup and shared runtime wiring
- serving workspace configuration
- reading and writing annotation records through the route layer
- managing background-job registries and shared polling/log infrastructure
- publishing additive WebSocket job events through the sidecar endpoint
- coordinating auth, OpenAPI, and HTTP MCP serving
- serving the built frontend for non-dev/local-server usage

The backend is not just a thin file server. It is the orchestration layer for PARSE's workflow-specific automation, while `python/server_routes/` now owns most HTTP-domain logic.

## Hybrid data architecture

PARSE uses a layered data model rather than a single monolithic database.

```mermaid
flowchart TD
    Audio[Source / working audio] --> Ann[annotations/<Speaker>.json]
    Ann --> Compare[Comparative computation]
    Compare --> Enrich[parse-enrichments.json]
    Ann --> Export[LingPy TSV / NEXUS / ELAN / TextGrid]
    Enrich --> Export
    Tags[Zustand tagStore persistence] --> AnnotateUI[Annotate mode]
    Tags --> CompareUI[Compare mode]
```

### 1. Live annotations

Primary speaker-level data lives in:

- `annotations/<Speaker>.json`
- or the canonical `.parse.json` variant where present

These files are the primary source of truth for time-aligned annotation work.

The current README emphasizes an important rule: timestamps are not treated as disposable AI output. Timing remains central to the review workflow.

### 2. Computed enrichments

Comparative overlays live in:

- `parse-enrichments.json`

This layer stores computed comparative structures such as:

- cognate sets
- similarity signals
- borrowing-related overlays
- lexeme notes
- manual overrides layered onto computed output

The point of the enrichments layer is to preserve comparative structure without collapsing the original annotation record into a purely derived format.

### 3. Tags

The tag system is shared across Annotate and Compare.

The current README describes it as a **Zustand `tagStore` persisted to localStorage**, scoped to the project and reused across workflows.

### 4. Transcript and analysis sidecars

PARSE also depends on supporting artifacts such as:

- `coarse_transcripts/<speaker>.json`
- `peaks/<Speaker>.json`
- optional import/legacy transcript CSVs
- `source_index.json`

These are not the same thing as the main annotation truth, but they materially support search, alignment, import, and visualization.

## Workspace-first design

PARSE can run directly from the repo, but its architecture is explicitly workspace-friendly.

When `PARSE_WORKSPACE_ROOT` is set, runtime writes and imports should land in that workspace rather than the bare repository tree.

This matters because PARSE is designed for:

- copied source audio
- imported processed artifacts
- persistent chat memory
- iterative fieldwork data preparation

In other words, the architecture assumes the active research workspace may be larger and more dynamic than the git checkout itself.

## AI provider architecture

PARSE routes different tasks to different provider families.

```mermaid
flowchart LR
    STT[STT request] --> FW[faster-whisper / Whisper API]
    ORTH[ORTH request] --> HF[HF Transformers FP32\nrazhan/whisper-base-sdh]
    ORTH -. legacy opt-in .-> CT2[faster-whisper / CT2]
    Align[Forced alignment] --> W2V[wav2vec2-xlsr-53-espeak-cv-ft]
    IPA[Acoustic IPA] --> W2V
    Chat[AI chat dock] --> LLM[OpenAI or xAI]
```

### ORTH backend choice (2026-05-01)

ORTH now defaults to `ortho.backend = "hf"` ([PR #218](https://github.com/ArdeleanLucas/PARSE/pull/218)), implemented by `HFWhisperProvider`
with Hugging Face Transformers FP32 PyTorch on `razhan/whisper-base-sdh`. The
first load may download roughly 280 MB into the standard Hugging Face cache at
`~/.cache/huggingface/`. The legacy CT2 path remains selectable with
`ortho.backend = "faster-whisper"` and a local CTranslate2 `ortho.model_path`,
but it is no longer recommended for Razhan SDH ORTH: on Lucas's RTX 5090,
HF Transformers was 16x faster on Saha01 and eliminated the 35.7% Latin /
Cyrillic / CJK contamination seen in the CT2 path.

This separation is important conceptually:

- speech recognition is not conflated with orthographic transcription
- orthographic transcription is not conflated with IPA generation
- workflow chat is not treated as the engine of alignment or export logic

## Lexical Anchor Alignment System

The **Lexical Anchor Alignment System** is the core PARSE feature for locating repeated lexical items in long recordings.

### Problem it solves

Long elicitation recordings often contain:

- conversational framing
- interviewer prompts
- repeated productions
- metalinguistic commentary
- ambient noise

A purely manual search process does not scale well across many speakers and concepts.

### Two-signal candidate ranking

```mermaid
flowchart TD
    Input[Target variants + optional concept_id] --> A[Signal A: within-speaker repetition]
    Input --> B[Signal B: cross-speaker concept matching]
    A --> Score[Weighted candidate score]
    B --> Score
    Score --> Ranked[Ranked candidate time ranges]
    Ranked --> Confirm[Human confirmation in Annotate mode]
    Confirm --> Anchors[confirmed_anchors sidecar]
    Anchors --> Future[Improved cross-speaker evidence for later speakers]
```

#### Signal A — within-speaker repetition detection

PARSE looks for repeated phonetically similar forms within a short time window. This is motivated by elicitation behavior where the same target form may be repeated several times in succession.

#### Signal B — cross-speaker concept matching

PARSE compares unassigned material against verified annotations from other speakers for the same concept using exact, fuzzy, phonetic-rule, and positional strategies.

#### Current confidence formula

```text
confidence = 0.50 × phonetic + 0.25 × repetition + 0.15 × positional + 0.10 × cluster
```

The positional component uses a 45-second tolerance window around the expected cross-speaker median timestamp.

### Human-in-the-loop design

Architecturally, this system is ranking-and-review, not auto-commit.

The annotator verifies a candidate, adjusts boundaries if needed, and explicitly confirms it. Confirmed anchors are then written to `AnnotationRecord.confirmed_anchors[concept_id]`, strengthening the cross-speaker signal for the remaining speakers.

## CLEF provider registry

**CLEF** (Contact Lexeme Explorer Feature) is the contact-language evidence layer used during borrowing adjudication in Compare mode.

It is implemented as a provider registry under `python/compare/providers/`.

### Registry shape

The current registry exposes a 10-provider stack in this priority order:

- `csv_override`
- `lingpy_wordlist`
- `pycldf`
- `pylexibank`
- `asjp`
- `cldf`
- `wikidata`
- `wiktionary`
- `literature`
- `grok_llm`

`grok_llm` is the xAI/Grok LLM fallback. It runs last after citable/local providers and is not a Grokipedia.com scrape/provider.

Recent CLEF hardening added exact doculect matching for local CLDF/Lexibank-style data, source/provenance reporting, provider-warning surfacing, form-selection persistence, and `POST /api/clef/clear` / `clef_clear_data` reset support.

### Architectural role of CLEF

```mermaid
flowchart LR
    CompareRow[Compare row / candidate borrowing case] --> CLEFReq[Contact lexeme request]
    CLEFReq --> Registry[Provider registry]
    Registry --> Sources[External and local lexical sources]
    Sources --> Evidence[Reference forms + coverage]
    Evidence --> Panel[ContactLexemePanel]
    Panel --> Decision[Borrowing adjudication]
```

CLEF is intentionally separated from the main annotation store. It augments comparison with external evidence rather than overwriting the primary annotation record.

## Concept-scoped pipeline reruns

The annotation compute layer now supports three run modes across HTTP, frontend batch orchestration, MCP workflow macros, and the public `parse_mcp` typings:

- `full` — whole-speaker behavior, preserved as the default.
- `concept-windows` — process concept-tier windows, optionally narrowed by `concept_ids`.
- `edited-only` — process only concept-tier rows marked `manuallyAdjusted`, optionally narrowed by `concept_ids`.

Non-full backend results include `affected_concepts` so the React workstation can refresh rows touched by a scoped rerun without repainting unrelated concept rows. This scoped refresh is advisory: after IPA, ORTH, STT, or BND compute completion, the workstation still reloads the completed speaker annotation from disk so persisted tier writes are canonical. The frontend run preview also carries `runMode` into its cell computation: concept-window and edited-only IPA cells may be runnable despite stale full-mode `ipa.can_run=false` when ORTH/concept-tier presence is observable, while full mode and pure-empty concept-window speakers stay blocked. Empty edited-only requests return a no-op payload rather than scheduling an empty background job. Concept-window STT/ORTH deliberately avoid English concept/gloss `initial_prompt` seeding and resolve language from request payload or annotation metadata before falling back to Whisper auto-detect.

## Chat tool architecture

The in-app assistant works through `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`).

Current counts:

- **57** built-in PARSE chat tools
- **57** default MCP task tools via `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`)
- **61** total default MCP adapter tools including 3 workflow macros + `mcp_get_exposure_mode`
- **42** total legacy curated opt-out tools when `config/mcp_config.json` sets `{ "expose_all_tools": false }`

This separation matters architecturally:

- the browser assistant can use the broader tool surface
- external MCP clients get the full safe task surface by default, with a legacy curated opt-out available through `expose_all_tools=false`
- the system stays bounded to PARSE-specific workflows rather than arbitrary shell access

## Export architecture

PARSE's export layer exists to carry reviewed annotation and comparative decisions into downstream analysis.

Current export paths mentioned in the README and code include:

- LingPy TSV
- NEXUS
- annotations CSV
- ELAN XML
- Praat TextGrid

These exports are downstream products of the annotation + enrichment layers rather than independent sources of truth.

## Design principles visible in the current architecture

Several design principles recur across the current implementation:

1. **Timestamps remain central** — PARSE is not a text-only annotation tool
2. **Human review stays explicit** — automation ranks, pre-fills, or computes, but confirmation remains visible
3. **Modes share one workspace** — Annotate and Compare are not disconnected applications
4. **AI is task-routed** — different providers handle different kinds of work
5. **Research outputs matter** — export is part of the architecture, not an afterthought

## Related docs

- Setup and runtime details: [Getting Started](./getting-started.md)
- User workflow walkthrough: [User Guide](./user-guide.md)
- Provider and tool surface details: [AI Integration](./ai-integration.md)
- Extension points and project layout: [Developer Guide](./developer-guide.md)
