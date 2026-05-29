# Developer Guide

> Last updated: 2026-05-14
>
> This guide is for contributors working on the active PARSE codebase: the React + Vite frontend in `src/`, the Python backend in `python/`, and the current workflow-specific documentation split under `docs/`.

## Project summary

PARSE is a browser-based dual-mode workstation for linguistic fieldwork and historical-comparative analysis.

Current architectural highlights:

- **Frontend**: React 18 + TypeScript + Vite
- **Backend**: Python API server in `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
- **Modes**: Annotate (`/`) and Compare (`/compare`) in one unified shell
- **Data**: per-speaker annotation JSON (`AnnotationRecord.confirmed_anchors`, `concept_tags`, IPA review sidecars), `parse-enrichments.json`, and survey/source sidecars such as `survey-overlap.json`
- **AI**: task-routed provider system for STT, ORTH, acoustic IPA, and chat
- **Compute**: chunk-aware long-file STT/ORTH, nested full-mode STT/ORTH/IPA subprocess isolation, and unified stage device resolution
- **Automation**: built-in chat tooling plus MCP server mode

## Repository structure

```text
index.html
src/
  App.tsx
  ParseUI.tsx                    -- unified workstation shell
  api/
    client.ts                    -- barrel only
    contracts/                   -- concrete HTTP helpers grouped by contract family
    types.ts                     -- shared TypeScript shapes still reused across families
  components/
    annotate/
      annotate-views/            -- concrete annotate workstation modules
    compare/
      compare-panels/            -- concrete compare workstation modules
    compute/
      clef/                      -- concrete CLEF modal/report modules
    parse/
      right-panel/               -- extracted parse right-panel tab content
    shared/
  hooks/
    wave-surfer/                 -- concrete WaveSurfer hook pieces
    batch-pipeline/              -- concrete batch-pipeline hook pieces
  stores/
    annotationStore.ts           -- barrel only
    annotation/                  -- concrete annotation-store slices/helpers
python/
  server.py                      -- thin HTTP orchestrator
  server_routes/                 -- concrete route-domain modules
  adapters/
    mcp_adapter.py               -- thin stdio entrypoint
    mcp/                         -- concrete MCP env/transport/schema/dispatch modules
  ai/
    chat_tools.py                -- registry/orchestrator only
    tools/                       -- concrete tool implementations by domain family
    chat_tools/                  -- earlier extracted tool bundles by family
    provider.py                  -- base provider surface only
    providers/                   -- concrete provider implementations
  external_api/                  -- OpenAPI + HTTP MCP + streaming helpers
  compare/                       -- comparative logic and CLEF providers
  packages/parse_mcp/            -- publishable Python wrapper package
parity/harness/                  -- oracle-vs-rebuild diff harness + tests
```

For the canonical "where does code live now?" reference, use [Post-decomp File Map](./architecture/post-decomp-file-map.md).

## Tech stack summary

### Frontend

- React 18
- TypeScript
- Vite
- Zustand
- Tailwind CSS v3
- WaveSurfer 7
- Lucide icons

### Backend

- Python 3.10–3.12
- local HTTP server in `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
- additive WebSocket job-streaming sidecar in `python/external_api/streaming.py` (`PARSE_WS_PORT`, default `8767`)
- OpenAPI 3.1 generation + interactive docs (`/openapi.json`, `/docs`, `/redoc`)
- HTTP MCP bridge for schema discovery + tool execution (`/api/mcp/*`)
- background job orchestration for STT / normalize / compute / chat
- JSON-file persistence for runtime state

### AI / speech stack

- faster-whisper for STT and legacy CT2 ORTH opt-in
- Hugging Face Transformers for default Razhan ORTH (`HFWhisperProvider`)
- CTranslate2 for faster-whisper-backed STT / legacy ORTH
- Razhan (`razhan/whisper-base-sdh`)
- Silero VAD for faster-whisper-era segmentation
- wav2vec2 (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`)
- OpenAI and xAI for workflow chat

## Local development flow

### Preferred launcher

Use the tracked launcher from the repo root:

```bash
./scripts/parse-run.sh
```

This:

- integrates latest code (unless skipped)
- clears stale Python/Vite processes
- starts the backend on `8766`
- starts Vite on `5173`
- prints the active URLs
- preserves the current `parse-run.sh` launcher behavior, including port preflight checks and Windows-process cleanup when `PARSE_PY` points at a Windows `python.exe`

### Manual launch

If you need separate terminals:

```bash
cp config/ai_config.example.json config/ai_config.json

# Terminal 1
# thin orchestrator entrypoint; concrete route logic lives in python/server_routes/
/path/to/python python/server.py

# Terminal 2
npm install
npm run dev
```

### Built frontend path

For non-dev/local-server usage:

```bash
npm run build
/path/to/python python/server.py
```

The Python backend can then serve the built frontend from `http://localhost:8766/`.

### WebSocket job streaming

The backend now also exposes an additive realtime stream beside the HTTP API:

- environment variable: `PARSE_WS_PORT`
- default port: `8767`
- endpoint shape: `ws://localhost:8767/ws/jobs/{jobId}`

This sidecar is optional. Existing HTTP polling remains supported and is still the baseline compatibility path.

Current v1 streamed event names:

- `job.snapshot`
- `job.progress`
- `job.log`
- `stt.segment`
- `job.complete`
- `job.error`

Example Python client:

```python
import json
from websockets.sync.client import connect

job_id = "stt-abc123"
with connect(f"ws://127.0.0.1:8767/ws/jobs/{job_id}") as ws:
    while True:
        event = json.loads(ws.recv())
        print(event["event"], event["payload"])
        if event["event"] in {"job.complete", "job.error"}:
            break
```

For STT jobs, `stt.segment` packets are provisional progress signals for UX and agent steering. The persisted cache/result written on completion remains the canonical artifact.

### Compute runtime modes and deployment notes

The current backend runtime is not limited to one execution model.

It supports:

- `thread` mode — the default in-process path
- `subprocess` mode — useful when isolating compute execution matters more than startup time
- `persistent` mode — keeps the wav2vec2-heavy worker warm across jobs

Relevant knobs and files:

- `PARSE_COMPUTE_MODE` or `python python/server.py --compute-mode=...`; `scripts/parse-run.sh` warns when the mode is unset
- `PARSE_USE_PERSISTENT_WORKER=true` for the persistent-worker path
- `PARSE_FULL_PIPELINE_MIN_MEM_GB` for the host-memory preflight that turns low-memory full-pipeline starts into structured `oom_suspect` job errors
- `PARSE_JOB_SNAPSHOT_DIR` for durable job snapshots; otherwise snapshots live under the workspace `.parse/jobs` directory and non-terminal records recover after restart as `server_restarted`
- `PARSE_ACTIVE_JOBS_TERMINAL_DWELL_SEC` for how long `/api/jobs/active` keeps terminal complete/error/cancelled jobs visible to the header strip (default 10s, clamped to 0-120s)
- `GET /api/worker/status` for persistent-worker health checks
- `deploy/pm2-ecosystem.config.cjs` for PM2-supervised deployments
- `POST /api/compute/{jobId}/cancel` for cooperative compute cancellation; STT/ORTH observe it between chunks/windows and can return `cancelled` or `partial_cancelled`
- `POST /api/lexeme/run_ortho` / `POST /api/lexeme/run_ipa` for reviewer-triggered interval reruns; default behavior starts tracked compute jobs `lexeme_rerun_ortho` / `lexeme_rerun_ipa`, and `async=false` is deprecated synchronous compatibility
- `POST /api/annotations/intervals/delete` for deleting one selected elicitation interval and same-time mirror rows without deleting the canonical concept row
- `GET /api/survey-overlap` and `POST /api/survey-overlap` for source/survey labels, color coding, concept links, and per-speaker survey choices
- `POST /api/concepts/{conceptId}/survey-links` and `DELETE /api/concepts/{conceptId}/survey-links` for cross-survey link CRUD against the `concept_survey_links` sidecar (not `concepts.csv`)
- `POST /api/concepts/relink-by-gloss` for cross-survey concept consolidation by canonical gloss (dry-run + apply with backups; fuzzy candidates are never auto-applied)
- `POST /api/concepts/by-tag` and `POST /api/lexemes/rerun-by-tag` for tag-filtered concept queries and job-tracked tag-filtered ORTH/IPA reruns (`lexemes_rerun_by_tag`; `async=false` only for deprecated synchronous compatibility). Shared resolution lives in `python/app/services/tag_resolver.py`; handlers in `python/app/http/tag_filtered_rerun_handlers.py`; route shim in `python/server_routes/tag_filtered_rerun.py`.
- `POST /api/locks/cleanup` plus startup cleanup for stale speaker-lock recovery; cleanup deletes stale `*.lock` files only and never kills processes

Compute architecture details now live in:

- [Compute architecture](./architecture/compute.md) — worker mental model, launcher modes, STT/ORTH chunking, subprocess isolation, device resolver, result contract
- [Worker process architecture](./architecture/worker-processes.md) — process topology and regression gates
- [Environment variables](./reference/environment-variables.md) — operator knobs for chunks, devices, timeouts, ports, and workspace roots

If you use PM2, keep `cwd` pointed at the **live workspace** rather than the bare git checkout so runtime artifacts land where the active UI expects them.

## Workspace model

PARSE can run directly in the repo, but the intended fieldwork architecture is workspace-first.

When `PARSE_WORKSPACE_ROOT` is set:

- runtime files land in that workspace
- imports hydrate that workspace
- the UI reflects the live workspace behind `/api/config`

Contributors working on import, annotation, or automation features should always remember that the active project state may be outside the git checkout.

## Frontend development rules that matter in practice

The current PARSE architecture expects:

- API traffic to go through `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/`)
- shared typed contracts to live in `src/api/types.ts` plus helper-local contract-family modules
- single-lexeme reruns, survey-overlap updates, add-elicitation / interval-delete flows, and concept-linking changes to use the existing typed API helpers; do not add bare `fetch()` from components
- data persistence to flow through the established stores and backend routes, especially `AnnotationRecord.concept_tags` for speaker-local tag membership
- the unified shell model to remain the organizing principle rather than splitting Annotate and Compare into isolated apps again
- contributors to verify whether a top-level `.tsx`/`.ts` file is now a barrel before adding new logic directly into it

For implementation-level architectural context, see [Architecture](./architecture.md) and [Post-decomp File Map](./architecture/post-decomp-file-map.md).

## Build and validation

Before pushing PARSE changes, run the current project gates:

```bash
npx vitest run
./node_modules/.bin/tsc --noEmit
```

These are the baseline frontend TypeScript and test checks called out in the current PARSE instructions. Backend/server changes should also run targeted `PYTHONPATH=python python3 -m pytest ...` coverage plus `uvx ruff check python/ --select E9,F63,F7,F82` before push.

Two additional realities are worth documenting explicitly:

- the project is still in active development, so full browser regression and export verification should be treated as ongoing validation work rather than assumed completed release guarantees
- schema compatibility between frontend and backend is enforced through `/api/config`; if that payload changes incompatibly, update the version constant in both `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) and `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`) in the same change

For documentation-only work, you should still at minimum:

- read back the changed Markdown files
- confirm relative links
- check `git diff` for unintended churn


## Debugging chunked or isolated compute jobs

When a long STT/ORTH/IPA job misbehaves, debug the job layer before changing model code.

1. Identify the job with `GET /api/jobs/active`, `jobs_list_active`, or the UI header strip.
2. Poll the terminal result with `stt_status`, `stt_word_level_status`, `compute_status`, or `job_status`.
3. Inspect `result.chunks[]` or `result.results.<step>.chunks[]` for the failed `span`, `status`, and `error_code`.
4. Read `job_logs` for the same `jobId`; nested subprocess crashes should be serialized with tracebacks and crash-log tails.
5. Check the stage result `device` and completion logs before assuming CUDA/CPU placement.
6. Reproduce with smaller chunks (`PARSE_STT_DEFAULT_CHUNK_MINUTES` / `PARSE_ORTH_DEFAULT_CHUNK_MINUTES`) before disabling chunking.

Maintenance rules:

- Keep `chunks[]` job-result-only; do not persist it into `coarse_transcripts/<speaker>.json`.
- Use `install_child_tee()` for any spawned child log file so live progress remains visible in parent stderr.
- Add/update [Compute architecture](./architecture/compute.md), [Worker process architecture](./architecture/worker-processes.md), [MCP schema](./mcp/schema.md), and [Environment variables](./reference/environment-variables.md) when changing the compute contract.

## Documentation layout after the restructure

The top-level docs now serve distinct audiences more cleanly:

- `docs/getting-started.md` — install, launch, config, troubleshooting
- `docs/getting-started-external-agents.md` — agent-facing MCP + HTTP automation guide
- `docs/user-guide.md` — end-user workflow
- `docs/ai-integration.md` — providers, models, chat tool surface
- `docs/api-reference.md` — HTTP + MCP reference
- `docs/reference/environment-variables.md` — operator-facing runtime env vars
- `docs/architecture.md` plus `docs/architecture/` — system design, data model, compute, and worker topology
- `docs/release-notes/` — release/change summaries for major shipped series
- `docs/developer-guide.md` — contributor-facing implementation guide
- `docs/research-context.md` — research and citation framing

Existing planning and historical material remains available under the existing `docs/`, `docs/plans/`, and `docs/archive/` structure.

## How to add a new HTTP endpoint

When adding an endpoint, keep the client/server contract explicit.

### 1. Add the server route

Implement the concrete route handler in the appropriate `python/server_routes/<domain>.py` module, then wire it through the thin `python/server.py` orchestrator.

### 2. Add or update the typed client helper

Expose the route from the correct `src/api/contracts/*.ts` file and re-export it through `src/api/client.ts` when the helper belongs on the public client surface.

This keeps the frontend on a single typed access layer instead of scattering raw `fetch()` calls.

### 3. Update shared types if needed

If the payload shape changes, update `src/api/types.ts` or the helper-local interfaces.

### 4. Update the docs

At minimum update:

- `docs/api-reference.md`
- `docs/architecture.md` if the new route changes the data model or workflow surface
- `docs/architecture/post-decomp-file-map.md` if the route introduces a new long-lived module family
- the root `README.md` if the change is user-visible enough to belong on the landing page

## How to add a new WebSocket stream

PARSE's current realtime transport is intentionally narrow: a dedicated per-job stream layered on top of the existing HTTP server rather than a framework migration.

When extending it:

1. Prefer reusing the existing job registry in `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) rather than inventing a parallel state store.
2. Publish typed envelopes through `python/external_api/streaming.py`.
3. Keep polling endpoints working; streaming must stay additive, never mandatory.
4. Use stable event names (`job.progress`, `job.log`, `stt.segment`, etc.).
5. Document any new event types in `docs/api-reference.md` and `AGENTS.md`.
6. Test event presence without over-specifying incidental ordering unless ordering is part of the explicit contract.

## How to add a new chat tool

The built-in assistant works through `python/ai/chat_tools.py`, but that file is now the registry/orchestrator layer rather than the main home for concrete tool logic.

For high-level MCP-only workflow macros, use `python/ai/workflow_tools.py` instead. Those tools should stay thin orchestration layers over existing low-level tool handlers and publish their own `ChatToolSpec` metadata.

A new tool should follow this pattern:

1. Implement the concrete behavior in the right `python/ai/tools/<category>_tools.py` module or the existing `python/ai/chat_tools/<family>.py` bundle if that family is already grouped there
2. Register or aggregate the tool through `python/ai/chat_tools.py`
3. Decide whether the tool is:
   - read-only / preview
   - job-triggering
   - alignment / correction
   - tag-related
   - write / export / merge
4. Update `docs/ai-integration.md` and `docs/agent-skills/parse-mcp-tools/` to keep the live tool list current
5. If the tool should also be exposed externally, update the MCP adapter modules and `docs/api-reference.md`

### Why this matters

PARSE's AI layer is designed around **bounded workflow tools**, not arbitrary shell execution. New tools should preserve that design discipline.

## How to expose a tool over MCP

The MCP adapter starts at `python/adapters/mcp_adapter.py`, but most implementation work now belongs in `python/adapters/mcp/`.

To expose a tool over MCP:

1. Ensure the underlying functionality already exists in `ParseChatTools` or `WorkflowTools`
2. Add the concrete adapter/schema/dispatch support in the appropriate `python/adapters/mcp/` module and keep `python/adapters/mcp_adapter.py` as the thin entrypoint
3. Keep parameter naming and documentation aligned with the underlying tool
4. Re-check the exported-tool count and update docs if the MCP subset changed

The adapter is intentionally a curated PARSE tool surface. Low-level browser/chat tools live in `ParseChatTools`; high-level agent workflow macros live in `WorkflowTools`.

## External API standardization points

Task 5 adds two more extension surfaces that matter for contributors:

1. **OpenAPI builder** — `python/external_api/openapi.py`
   - keep the served `/openapi.json` spec aligned with real routes in `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
   - when adding HTTP routes, update the OpenAPI path table in the same PR
2. **HTTP MCP bridge** — `python/external_api/catalog.py` + `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
   - exposes MCP tool schemas over HTTP
   - executes MCP-visible tools over `POST /api/mcp/tools/{toolName}`
   - should reuse existing `ChatToolSpec` metadata rather than inventing parallel schemas
3. **Publishable wrapper package** — `python/packages/parse_mcp/`
   - keep discovery/execution behavior aligned with the HTTP MCP bridge
   - framework wrappers should remain thin adapters over the discovered tool schema
4. **WebSocket streaming sidecar** — `python/external_api/streaming.py` + `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`)
   - keep the per-job stream shape aligned with the live job registry
   - treat polling, callbacks, and streaming as complementary transports over the same job state
   - do not assume strict ordering between near-simultaneous events like `job.log` and `job.progress` unless the code explicitly enforces it

When adding or renaming MCP-visible tools, update all three layers together:
- stdio adapter
- HTTP MCP bridge
- `parse-mcp` package docs/tests

### Publishing `parse-mcp` to PyPI

When the package metadata or release contents change, validate and publish from the repo root.

1. Validate locally and build the release artifacts.
2. Test on TestPyPI first so you can confirm installability before the real release.
3. Publish the same version to PyPI only after the TestPyPI smoke check looks correct.

```bash
python3 -m pip install build twine
python3 -m pytest python/packages/parse_mcp/tests -q
python3 -m build python/packages/parse_mcp
python3 -m twine check python/packages/parse_mcp/dist/*
python3 -m twine upload --repository testpypi python/packages/parse_mcp/dist/*
python3 -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ parse-mcp
python3 -m twine upload python/packages/parse_mcp/dist/*
```

Release notes:
- preferred public package name: `parse-mcp`
- current metadata lives in `python/packages/parse_mcp/pyproject.toml`
- the repo owner should remain the primary PyPI maintainer
- publish to TestPyPI first when releasing a version for the first time or after metadata changes

## How to add or extend a CLEF provider

CLEF providers live under `python/compare/providers/`.

A provider change usually touches three layers:

1. provider implementation / metadata under `python/compare/providers/`
2. any server-side compute or coverage handling
3. Compare-mode UI surfaces that consume the results

When extending CLEF:

- keep the provider registry explicit
- keep the guided config surface aligned with the backend endpoints (`GET/POST /api/clef/config`, `GET /api/clef/catalog`, `GET /api/clef/providers`)
- keep the provenance / selection / reset endpoints aligned with the UI and agent surfaces (`GET /api/clef/sources-report`, `POST /api/clef/form-selections`, `POST /api/clef/clear`, MCP/chat tool `clef_clear_data`)
- remember that fresh workspaces may start without `config/sil_contact_languages.json`; backend init and UI copy should treat that as normal, not as a crash path
- document any new expectations around `config/sil_catalog_extra.json` if the language picker or catalog merge rules change
- preserve per-language ISO 15924 `script` hints when touching the catalog/config flow; `ClefConfigModal` and `GET/POST /api/clef/config` now round-trip them intentionally
- document new coverage or source assumptions
- update the provider list in user-facing docs if the provider set changes

The current CLEF UI also assumes:

- similarity columns are derived dynamically from `primary_contact_languages`, not hard-coded language slots
- the Reference Forms panel may show multiple forms per language
- bare-string Reference Forms are routed by explicit provider label first, then language `script` hint, then Unicode-block fallback
- per-form provenance may be available and should stay visible through the Sources Report modal
- form-selection state persists in `sil_contact_languages.json._meta.form_selections` and affects downstream similarity scoring

## Batch transcription modal semantics

`src/components/shared/TranscriptionRunModal.tsx` now has explicit per-step scope controls when selected speakers already have finalized output.

Current semantics:

- **Keep** (`overwrite=false`) is the default when a step collides with existing output
- **Overwrite** (`overwrite=true`) must be chosen explicitly per step
- the collisions bar only appears when the selected speakers actually have finalized output for at least one selected step

When changing this modal:

- keep the user-facing **Keep / Overwrite** wording aligned with the real payload semantics
- preserve the distinction between no-op keep behavior and destructive overwrite behavior in badges, summary text, and tooltips
- update `docs/user-guide.md` / `README.md` if the rerun semantics change materially

## Contributing guidelines

### Keep claims aligned with code

PARSE moves quickly. Documentation, API surface, and workflow details can drift unless they are updated together.

A good rule:

- if a feature changes the user workflow, update the relevant `docs/*.md`
- if it changes the route/tool surface, update `docs/api-reference.md`
- if it changes system shape, update `docs/architecture.md`
- if it changes the first impression of the project, update `README.md`

### Keep workflows explicit

PARSE is a fieldwork/research tool. Contributors should prefer:

- explicit job boundaries
- visible status reporting
- human-reviewable outputs
- reproducible export paths

### Preserve the workspace mindset

Be careful with any change that assumes the repo itself is the live data root. In active PARSE usage, the workspace may be external and mutable while the repo remains a code checkout.

## Related docs

- Runtime setup: [Getting Started](./getting-started.md)
- User workflow: [User Guide](./user-guide.md)
- AI providers and tool surface: [AI Integration](./ai-integration.md)
- System shape and data model: [Architecture](./architecture.md)
- Research/citation framing: [Research Context](./research-context.md)
