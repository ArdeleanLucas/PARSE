# Developer Guide

> Last updated: 2026-04-24
>
> This guide is for contributors working on the active PARSE codebase: the React + Vite frontend in `src/`, the Python backend in `python/`, and the current workflow-specific documentation split under `docs/`.

## Project summary

PARSE is a browser-based dual-mode workstation for linguistic fieldwork and historical-comparative analysis.

Current architectural highlights:

- **Frontend**: React 18 + TypeScript + Vite
- **Backend**: Python API server in `python/server.py`
- **Modes**: Annotate (`/`) and Compare (`/compare`) in one unified shell
- **Data**: per-speaker annotation JSON + `parse-enrichments.json`
- **AI**: task-routed provider system for STT, ORTH, acoustic IPA, and chat
- **Automation**: built-in chat tooling plus MCP server mode

## Repository structure

```text
index.html              -- React/Vite entry HTML
src/
  App.tsx               -- BrowserRouter shell → <ParseUI />
  ParseUI.tsx           -- Unified shell (Annotate + Compare + Tags + AI Chat)
  api/
    client.ts           -- Typed API client
    types.ts            -- Shared TypeScript types
  components/
    annotate/           -- Annotate mode components
    compare/            -- Compare mode components
    shared/             -- Shared components
  hooks/                -- React hooks
  stores/               -- Zustand stores
python/
  server.py             -- Backend API server + built frontend serving
  adapters/
    mcp_adapter.py      -- MCP adapter
  ai/
    chat_tools.py       -- ParseChatTools (50 tools)
    chat_orchestrator.py
    stt_pipeline.py
    forced_align.py
    ipa_transcribe.py
  external_api/         -- OpenAPI generation + HTTP MCP bridge helpers
  compare/
    providers/          -- CLEF provider registry and adapters
  shared/               -- Shared Python utilities
  packages/
    parse_mcp/          -- Publishable Python client/wrapper package
config/
  ai_config.example.json -- tracked template
  ai_config.json         -- machine-local config (gitignored)
annotations/            -- runtime annotation JSON
parse-enrichments.json  -- runtime comparative overlays
desktop/                -- Electron shell scaffold
docs/                   -- user, developer, research, and planning docs
dist/                   -- build output
```

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
- local HTTP server in `python/server.py`
- additive WebSocket job-streaming sidecar in `python/external_api/streaming.py` (`PARSE_WS_PORT`, default `8767`)
- OpenAPI 3.1 generation + interactive docs (`/openapi.json`, `/docs`, `/redoc`)
- HTTP MCP bridge for schema discovery + tool execution (`/api/mcp/*`)
- background job orchestration for STT / normalize / compute / chat
- JSON-file persistence for runtime state

### AI / speech stack

- faster-whisper
- CTranslate2
- Razhan (`razhan/whisper-base-sdh`)
- Silero VAD
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

- `PARSE_COMPUTE_MODE` or `python python/server.py --compute-mode=...`
- `PARSE_USE_PERSISTENT_WORKER=true` for the persistent-worker path
- `GET /api/worker/status` for persistent-worker health checks
- `deploy/pm2-ecosystem.config.cjs` for PM2-supervised deployments

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

- API traffic to go through `src/api/client.ts`
- shared typed contracts to live in `src/api/types.ts`
- data persistence to flow through the established stores and backend routes
- the unified shell model to remain the organizing principle rather than splitting Annotate and Compare into isolated apps again

For implementation-level architectural context, see [Architecture](./architecture.md).

## Build and validation

Before pushing PARSE changes, run the current project gates:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

These are the baseline TypeScript and test checks called out in the current PARSE instructions.

Two additional realities are worth documenting explicitly:

- the project is still in active development, so full browser regression and export verification should be treated as ongoing validation work rather than assumed completed release guarantees
- schema compatibility between frontend and backend is enforced through `/api/config`; if that payload changes incompatibly, update the version constant in both `python/server.py` and `src/api/client.ts` in the same change

For documentation-only work, you should still at minimum:

- read back the changed Markdown files
- confirm relative links
- check `git diff` for unintended churn

## Documentation layout after the restructure

The top-level docs now serve distinct audiences more cleanly:

- `docs/getting-started.md` — install, launch, config, troubleshooting
- `docs/getting-started-external-agents.md` — agent-facing MCP + HTTP automation guide
- `docs/user-guide.md` — end-user workflow
- `docs/ai-integration.md` — providers, models, chat tool surface
- `docs/api-reference.md` — HTTP + MCP reference
- `docs/architecture.md` — system design and data model
- `docs/developer-guide.md` — contributor-facing implementation guide
- `docs/research-context.md` — thesis and citation framing

Existing planning and historical material remains available under the existing `docs/`, `docs/plans/`, and `docs/archive/` structure.

## How to add a new HTTP endpoint

When adding an endpoint, keep the client/server contract explicit.

### 1. Add the server route

Implement the route in `python/server.py` by wiring it into the relevant dispatch method:

- `_dispatch_api_get`
- `_dispatch_api_post`
- `_dispatch_api_put`

### 2. Add or update the typed client helper

Expose the route from `src/api/client.ts`.

This keeps the frontend on a single typed access layer instead of scattering raw `fetch()` calls.

### 3. Update shared types if needed

If the payload shape changes, update `src/api/types.ts` or the helper-local interfaces.

### 4. Update the docs

At minimum update:

- `docs/api-reference.md`
- `docs/architecture.md` if the new route changes the data model or workflow surface
- the root `README.md` if the change is user-visible enough to belong on the landing page

## How to add a new WebSocket stream

PARSE's current realtime transport is intentionally narrow: a dedicated per-job stream layered on top of the existing HTTP server rather than a framework migration.

When extending it:

1. Prefer reusing the existing job registry in `python/server.py` rather than inventing a parallel state store.
2. Publish typed envelopes through `python/external_api/streaming.py`.
3. Keep polling endpoints working; streaming must stay additive, never mandatory.
4. Use stable event names (`job.progress`, `job.log`, `stt.segment`, etc.).
5. Document any new event types in `docs/api-reference.md` and `AGENTS.md`.
6. Test event presence without over-specifying incidental ordering unless ordering is part of the explicit contract.

## How to add a new chat tool

The built-in assistant works through `ParseChatTools` in `python/ai/chat_tools.py`.

For high-level MCP-only workflow macros, use `python/ai/workflow_tools.py` instead. Those tools should stay thin orchestration layers over existing low-level tool handlers and publish their own `ChatToolSpec` metadata.

A new tool should follow this pattern:

1. Add the new `ChatToolSpec` entry in `python/ai/chat_tools.py`
2. Implement the execution path and validation logic in the same tool layer
3. Decide whether the tool is:
   - read-only / preview
   - job-triggering
   - alignment / correction
   - tag-related
   - write / export / merge
4. Update `docs/ai-integration.md` to keep the 50-tool list current
5. If the tool should also be exposed externally, add it to the MCP adapter and update `docs/api-reference.md`

### Why this matters

PARSE's AI layer is designed around **bounded workflow tools**, not arbitrary shell execution. New tools should preserve that design discipline.

## How to expose a tool over MCP

The MCP adapter lives in `python/adapters/mcp_adapter.py`.

To expose a tool over MCP:

1. Ensure the underlying functionality already exists in `ParseChatTools` or `WorkflowTools`
2. Add a matching `@mcp.tool()` wrapper in `python/adapters/mcp_adapter.py`
3. Keep parameter naming and documentation aligned with the underlying tool
4. Re-check the exported-tool count and update docs if the MCP subset changed

The adapter is intentionally a curated PARSE tool surface. Low-level browser/chat tools live in `ParseChatTools`; high-level agent workflow macros live in `WorkflowTools`.

## External API standardization points

Task 5 adds two more extension surfaces that matter for contributors:

1. **OpenAPI builder** — `python/external_api/openapi.py`
   - keep the served `/openapi.json` spec aligned with real routes in `python/server.py`
   - when adding HTTP routes, update the OpenAPI path table in the same PR
2. **HTTP MCP bridge** — `python/external_api/catalog.py` + `python/server.py`
   - exposes MCP tool schemas over HTTP
   - executes MCP-visible tools over `POST /api/mcp/tools/{toolName}`
   - should reuse existing `ChatToolSpec` metadata rather than inventing parallel schemas
3. **Publishable wrapper package** — `python/packages/parse_mcp/`
   - keep discovery/execution behavior aligned with the HTTP MCP bridge
   - framework wrappers should remain thin adapters over the discovered tool schema
4. **WebSocket streaming sidecar** — `python/external_api/streaming.py` + `python/server.py`
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
- document new coverage or source assumptions
- update the provider list in user-facing docs if the provider set changes

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
- Thesis/citation framing: [Research Context](./research-context.md)
