# Post-decomposition file map

> Canonical PARSE module layout reference as of 2026-04-27. Use this page when you need the **current** layout rather than historical pre-decomposition paths mentioned in older plans or reports.

## Backend module map

### HTTP server and route domains
- `python/server.py` — thin orchestrator: startup, shared registries, route wiring, OpenAPI/HTTP MCP serving, built-frontend serving
- `python/server_routes/annotate.py` — annotation reads/writes, STT segments, lexeme search, offset flows tied to annotate workflows
- `python/server_routes/compare.py` — compare-mode data, tags, notes, pipeline state, comparative endpoints
- `python/server_routes/jobs.py` — generic job listing, job status, job logs, callback/status plumbing
- `python/server_routes/exports.py` — LingPy/NEXUS/media/export responses
- `python/server_routes/config.py` — `/api/config` and related workspace-config contract handling
- `python/server_routes/clef.py` — CLEF config/catalog/providers/sources-report/form-selections
- `python/server_routes/chat.py` — chat session/run/auth-adjacent AI routes exposed through the workstation API
- `python/server_routes/media.py` — spectrogram/static media helpers and related binary responses

### Chat tools
- `python/ai/chat_tools.py` — registry/orchestrator for `ParseChatTools`; treat it as the public aggregation point, not the place for most new tool logic
- `python/ai/tools/comparative_tools.py` — comparative/cognate/compare-mode tool implementations
- `python/ai/tools/contact_lexeme_tools.py` — CLEF/contact-language tool implementations
- `python/ai/tools/enrichment_tools.py` — enrichments/tags/notes/project-state tool implementations
- `python/ai/tools/export_tools.py` — export-related tool implementations
- `python/ai/tools/transform_tools.py` — transform/normalization/pipeline/tooling helpers
- `python/ai/tools/artifact_tools.py` — artifact/file/report-oriented tool implementations
- earlier grouped bundles remain under `python/ai/chat_tools/` for domain families such as annotation/enrichment/export where extracted logic already lives there
- `python/ai/workflow_tools.py` — high-level workflow macros layered over the lower-level tool surface

### MCP adapter
- `python/adapters/mcp_adapter.py` — thin stdio MCP entrypoint/orchestrator
- `python/adapters/mcp/env_config.py` — environment/config loading and exposure-mode resolution
- `python/adapters/mcp/transport.py` — server transport/bootstrap wiring
- `python/adapters/mcp/tool_dispatch.py` — MCP-visible tool dispatch and execution glue
- `python/adapters/mcp/schema.py` — schema/annotation/meta projection
- `python/adapters/mcp/error_envelope.py` — structured MCP error shaping

### Provider layer
- `python/ai/provider.py` — base provider ABC/shared routing surface; do not keep concrete provider logic here
- `python/ai/providers/xai.py` — xAI/Grok provider implementation
- `python/ai/providers/openai.py` — OpenAI provider implementation
- `python/ai/providers/ollama.py` — Ollama/local LLM provider implementation
- `python/ai/providers/local_whisper.py` — local Whisper/faster-whisper provider implementation
- `python/ai/providers/shared.py` — provider-shared helpers/constants

## Frontend module map

### API client
- `src/api/client.ts` — barrel only; import API helpers from here at call sites
- `src/api/contracts/annotation-data.ts`
- `src/api/contracts/project-config-and-pipeline-state.ts`
- `src/api/contracts/enrichments-tags-notes-imports.ts`
- `src/api/contracts/auth.ts`
- `src/api/contracts/stt-normalize-onboard.ts`
- `src/api/contracts/offset-tools.ts`
- `src/api/contracts/suggestions-lexeme-search.ts`
- `src/api/contracts/chat-and-generic-compute.ts`
- `src/api/contracts/job-observability.ts`
- `src/api/contracts/export-and-media.ts`
- `src/api/contracts/clef-contact-lexeme.ts`
- `src/api/contracts/shared.ts`

### Annotation store
- `src/stores/annotationStore.ts` — barrel only
- `src/stores/annotation/actions.ts` — mutation helpers/actions
- `src/stores/annotation/persistence.ts` — persistence/export/import-facing helpers
- `src/stores/annotation/selectors.ts` — selectors/derived reads
- `src/stores/annotation/types.ts` — annotation-store types/constants
- `src/stores/annotationStoreHistory.ts` — history/undo-redo support
- `src/stores/annotationStoreIntervals.ts` — interval-focused helpers and tests/supporting logic

### Compute / CLEF UI
- `src/components/compute/ClefConfigModal.tsx` — barrel only
- `src/components/compute/ClefSourcesReportModal.tsx` — barrel only
- `src/components/compute/ClefPopulateSummaryBanner.tsx` — barrel only
- concrete implementations live under `src/components/compute/clef/`

### Compare UI
- `src/components/compare/BorrowingPanel.tsx` — barrel only
- `src/components/compare/ConceptTable.tsx` — barrel only
- `src/components/compare/LexemeDetail.tsx` — barrel only
- `src/components/compare/CognateControls.tsx` — barrel only
- concrete compare-panel implementations live under `src/components/compare/compare-panels/`

### Annotate UI
- `src/components/annotate/AnnotateView.tsx` — barrel only
- `src/components/annotate/AnnotateMode.tsx` — barrel only
- `src/components/annotate/AnnotationPanel.tsx` — barrel only
- `src/components/annotate/LexemeSearchPanel.tsx` — barrel only
- concrete annotate-view implementations live under `src/components/annotate/annotate-views/`

### Hooks
- `src/hooks/useWaveSurfer.ts` — barrel only; concrete hook pieces live under `src/hooks/wave-surfer/`
- `src/hooks/useBatchPipelineJob.ts` — barrel only; concrete hook pieces live under `src/hooks/batch-pipeline/`

### Parse workstation shell
- `src/ParseUI.tsx` — still the unified shell entrypoint, but no longer the main place to look for every view-level implementation
- `src/components/parse/RightPanel.tsx` — thin shell; right-panel tab content now lives under `src/components/parse/right-panel/`

## Parity harness layout
- `parity/harness/runner.py` — diff-harness entrypoint; was the cutover-gate equivalence check (oracle vs rebuild). Post-cutover (2026-04-27) it remains as a historical artifact and self-consistency tool against `ArdeleanLucas/PARSE-pre-rebuild-archive`.
- `parity/harness/tests/` — unit tests for harness behavior
- `parity/harness/output/` — generated reports/artifacts
- `parity/harness/SIGNOFF.md` — owned signoff/status document; do not preempt in unrelated docs PRs
- CI now includes **Parity Diff Harness** as a first-class gate alongside schema/frontend/backend checks

## Where do I add X?
- **New HTTP route** → add the domain handler in `python/server_routes/<domain>.py`, then wire it through `python/server.py`
- **New chat tool implementation** → usually add concrete logic under `python/ai/tools/<category>_tools.py` (or the existing `python/ai/chat_tools/<family>.py` bundle if that family already lives there), then register/aggregate via `python/ai/chat_tools.py`
- **New MCP adapter behavior** → add concrete logic under `python/adapters/mcp/` and keep `python/adapters/mcp_adapter.py` as the thin entrypoint
- **New provider implementation** → add a module under `python/ai/providers/` and keep `python/ai/provider.py` as the abstract/shared layer
- **New frontend API helper** → add it in the right `src/api/contracts/*.ts` file and re-export through `src/api/client.ts`
- **New annotation-store selector/action/persistence helper** → add it under `src/stores/annotation/` and re-export through `src/stores/annotationStore.ts` only if needed by callers
- **New CLEF modal/report/config UI** → add the implementation under `src/components/compute/clef/`; keep the top-level compute file as a barrel if the public import path must stay stable
- **New compare panel** → add it under `src/components/compare/compare-panels/`, then preserve any stable top-level import via a barrel in `src/components/compare/`
- **New annotate view/panel** → add it under `src/components/annotate/annotate-views/`, then preserve stable top-level imports via the corresponding barrel in `src/components/annotate/`
- **New wave-surfer or batch-pipeline hook logic** → add it under `src/hooks/wave-surfer/` or `src/hooks/batch-pipeline/`, then re-export through the top-level hook barrel when appropriate
- **Need the current layout fast** → start with this file, then verify the exact barrel/orchestrator file in code before documenting details elsewhere
