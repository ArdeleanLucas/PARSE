# PARSE Desktop Product Architecture (Living Plan)

> **Living document (canonical):** this is the active plan for PARSE desktop packaging/evolution.
> 
> Update this file whenever architectural decisions, release assumptions, or packaging constraints change.
>
> **Last updated:** 2026-03-27  
> **Status:** Proposed architecture (pre-implementation)  
> **Scope:** Local desktop product foundation for macOS + Windows (Electron shell + local Python engine)

---

## 1) Why this document exists

PARSE currently runs as a local browser app plus Python server. Lucas wants a packaged local product experience (Praat/BEAST2-style) with:
- predictable install/launch behavior,
- minimal manual setup,
- robust local-only data handling,
- upgrade path from current PARSE without breaking active work.

This document defines the target architecture and staged rollout path.

---

## 2) Product goals and non-goals

## Goals

1. **Single-app desktop UX**
   - User installs PARSE, opens it, and works without manual server startup.

2. **Local-first execution**
   - Audio/transcripts/annotations stay local by default.
   - Cloud AI is optional and explicitly configured.

3. **Cross-platform parity (Windows + macOS)**
   - Same project format and core workflow on both platforms.

4. **Backwards-compatible project evolution**
   - Existing PARSE project artifacts remain usable (with migration where necessary).

5. **Incremental migration from today’s codebase**
   - Do not disrupt active streams (MC-245 exact-port compare shell, MC-246 built-in AI chat/toolbox).

## Non-goals (for this wave)

1. Linux packaging as first-class release target.
2. Multi-user/networked collaboration mode.
3. Cloud-hosted backend replacement.
4. Full plugin marketplace ecosystem.
5. Perfectly unified Annotate/Compare rewrite in a single release.

---

## 3) Product shape (target user experience)

PARSE Desktop ships as a standard installed app that:

1. Opens a native window (Electron shell).
2. Starts an internal local backend automatically.
3. Loads PARSE UI against that local backend.
4. Lets user open/create a project folder.
5. Persists settings, logs, model cache, and update channel in app-owned user-data directories.

### Target launch flow

1. User launches PARSE Desktop.
2. Splash/health check while backend starts.
3. “Open project / Create project” screen (or reopen last project).
4. UI opens in Annotate or Compare mode.
5. Background jobs (STT/compute/export) run locally with progress.

---

## 4) High-level architecture

## Recommended architecture: **Electron shell + loopback Python HTTP backend**

Reasoning: lowest migration risk because current frontend already expects HTTP API and static file serving.

```text
+---------------------------+        +--------------------------------------+
| Electron Main Process     |        | Python Backend Process               |
|---------------------------| spawn  |--------------------------------------|
| - app lifecycle           +------->| - static UI serving (parse/compare)  |
| - window creation         |        | - /api/* endpoints                   |
| - auto-update             |        | - job queue (stt/compute/export)     |
| - settings persistence    |        | - project IO + annotation IO          |
| - secure preload bridge   |        | - model orchestration                |
+-------------+-------------+        +------------------+-------------------+
              |                                            ^
              | loads http://127.0.0.1:<ephemeral_port>   |
              v                                            |
+---------------------------+                              |
| Renderer (PARSE UI)       |--- local HTTP API ----------+
| - parse.html / compare    |
| - existing JS modules     |
+---------------------------+
```

### Boundary decision

- **Primary boundary:** localhost HTTP (`127.0.0.1`, ephemeral port, auth token).
- **IPC use:** only for native shell actions (dialogs, OS integrations, logs, updates), not core linguistic logic.

This keeps existing frontend API usage mostly intact while still giving a secure desktop shell.

---

## 5) Process model details

## 5.1 Main process responsibilities

- Determine active project path (last project or user-selected).
- Start backend process with explicit args:
  - `--host 127.0.0.1`
  - `--port 0` (ephemeral)
  - `--project-root <path>`
  - `--auth-token <random>`
  - `--user-data-root <Electron userData path>`
- Wait for backend readiness handshake.
- Open BrowserWindow pointing to backend URL.
- Monitor backend process; restart/fail-fast with clear error UI.

## 5.2 Backend responsibilities

- Serve static UI and APIs from one origin.
- Manage annotation/enrichment/project persistence.
- Run long jobs with progress polling.
- Expose health + diagnostics endpoints.
- Enforce path safety relative to selected project root.

## 5.3 Renderer responsibilities

- UI state and interaction orchestration.
- Polling for long-running jobs via API.
- Display backend status/errors with actionable messages.

---

## 6) Project and file model

## 6.1 Project folder assumptions (desktop target)

Each PARSE project should be a self-contained folder with relative paths by default:

```text
<MyProject>/
  project.json
  source_index.json
  parse-enrichments.json
  annotations/
  transcripts/
  peaks/
  exports/
  audio/
    original/
    working/
  sync/
  logs/                (project-specific optional logs)
```

### Rules

1. `project.json` is canonical for project metadata.
2. Paths in `project.json` should be project-relative unless explicitly marked external.
3. External file references (if allowed) must be explicit and validated.

## 6.2 App-owned user-data directories

Use Electron `app.getPath('userData')` as root.

### macOS
`~/Library/Application Support/PARSE/`

### Windows
`%APPDATA%\PARSE\`

### Proposed layout

```text
<userData>/
  settings.json
  logs/
    main.log
    renderer.log
    backend.log
  cache/
    temp/
    waveform/
    stt/
  models/
    manifest.json
    whisper/
  runtime/
    python/            (bundled/managed runtime assets)
  backups/
    migrations/
```

---

## 7) Path strategy (portability-critical)

## Principles

1. **No hardcoded machine/user paths in shipped defaults**.
2. **No `/mnt/c/...` assumptions in runtime paths**.
3. **No dependence on current working directory as implicit project selector**.

## Required path behavior

- Backend must accept explicit `project_root` at startup.
- All file IO resolves from that root or approved app dirs.
- Path normalization + traversal prevention remains mandatory.
- UI should show resolved paths in Settings > Storage for debugging.

---

## 8) Python runtime strategy

## 8.1 Target strategy by phase

### Alpha (internal)
- Allow system Python for speed of iteration.
- Desktop preflight checks required at startup.

### Beta
- Bundle managed Python runtime per OS/arch.
- Bundle core wheels (offline install capability).

### Public
- Ship fully managed Python runtime with deterministic dependency set.
- No external Python requirement for normal users.

## 8.2 Runtime management requirements

1. Runtime version pinned (example: Python 3.11.x target; final pin TBD).
2. Dependency installation deterministic (lockfile + wheelhouse).
3. Backend startup must emit explicit diagnostics when dependency missing.
4. Runtime integrity check on app startup (version + hash metadata).

---

## 9) Model and dependency strategy

## 9.1 Dependency tiers

1. **Core required** (always installed)
   - server/runtime essentials
   - annotation IO
   - export + baseline audio processing

2. **Heavy local AI optional**
   - faster-whisper + ctranslate2 stack
   - LingPy and advanced compute stack

3. **Cloud AI optional**
   - OpenAI/xAI/Ollama connectors (provider-dependent)

## 9.2 Model strategy

- Maintain a **model manifest** (name, version, checksum, size, license, min runtime).
- User-selectable model cache location (default in app user-data models dir).
- Download manager with pause/resume + checksum verification.
- Clear fallback when preferred model unavailable.

## 9.3 Known model portability requirement

- The `razhan/whisper-base-sdh` faster-whisper path must use a CT2-compatible model artifact in production flow.
- Do **not** depend on ad-hoc local HF cache structure.

---

## 10) CPU baseline and optional GPU acceleration

## 10.1 CPU baseline (must always work)

- CPU-only mode is mandatory and should be default-safe.
- STT and compute jobs may run slower but must remain functional.
- Provide explicit performance expectations in UI.

## 10.2 GPU strategy

- GPU acceleration is optional enhancement, never hard requirement.
- Runtime capability detection should happen at startup and on demand.
- If GPU init fails, auto-fallback to CPU with clear messaging.

### Phase policy

- **Alpha:** prioritize CPU correctness.
- **Beta:** Windows CUDA path support with fallback.
- **Public:** broaden support only after reliability metrics are acceptable.

---

## 11) Electron responsibilities vs backend responsibilities

## Electron shell responsibilities

- App lifecycle, menus, and native dialogs.
- Project open/create/recent-project UX.
- Backend child-process lifecycle and crash handling.
- Update channel + installation orchestration.
- Secure preload API for limited native operations.

## Backend responsibilities

- Domain logic (annotations, compare, enrichments, exports).
- AI orchestration and long-running jobs.
- Project persistence/migration operations.
- API contract stability for renderer.

**Rule:** domain logic stays in backend; shell remains orchestration and OS integration.

---

## 12) Settings UX plan

Desktop Settings should be explicit and debuggable.

## Sections

1. **General**
   - language/theme/recent projects
2. **Project**
   - active project root, project validation, migration status
3. **Storage**
   - user-data directories, cache size, cleanup actions
4. **AI Providers**
   - provider selection, API key env mapping, test connection
5. **Models**
   - installed models, location, download/remove
6. **Performance**
   - CPU/GPU mode, worker limits, job concurrency
7. **Advanced**
   - diagnostics bundle export, verbose logging toggle
8. **Updates**
   - channel (alpha/beta/stable), current version, check/update now

---

## 13) Installer and update strategy (macOS + Windows)

## 13.1 Packaging targets

## Windows
- NSIS installer (per-user default, admin optional).
- Signed executable/installers required before public release.

## macOS
- Signed + notarized app.
- DMG and ZIP artifacts for distribution/update compatibility.
- Separate arm64/x64 artifacts initially (universal binary optional later).

## 13.2 Update channels

- `alpha` (internal dogfood)
- `beta` (external testers)
- `stable` (public)

Use staged rollout with rollback path:
1. download update,
2. integrity validation,
3. install on next restart,
4. migration preflight,
5. health-check + rollback trigger if startup fails.

---

## 14) Security model (localhost/IPC boundary)

## Required security changes for desktop packaging

1. Bind backend to `127.0.0.1` by default (not `0.0.0.0`).
2. Remove wildcard CORS defaults for desktop runtime.
3. Require per-session auth token between renderer and backend.
4. Enforce strict CSP and eliminate remote script dependency in packaged build.
5. BrowserWindow hardening:
   - `contextIsolation: true`
   - `nodeIntegration: false`
   - `sandbox: true` where feasible
   - disable unexpected navigation/new-window creation.
6. IPC allowlist only (no generic eval/exec bridge).

---

## 15) Staged milestones (alpha → beta → public)

## Milestone A — Desktop Spike (internal)

**Goal:** prove Electron + backend loopback boot and basic project open.

Exit criteria:
- App launches and starts backend automatically.
- `parse.html` and `compare.html` open from desktop shell.
- Basic annotation read/write works on a sample project.

## Milestone B — Internal Alpha

**Goal:** daily usable for core team on at least one OS.

Exit criteria:
- Stable startup and shutdown behavior.
- Project open/create/recent functionality.
- Logs + diagnostics bundle available.
- No manual server startup needed.

## Milestone C — Cross-platform Beta (Windows + macOS)

**Goal:** external tester readiness.

Exit criteria:
- Signed installers.
- Managed Python runtime packaged.
- Update channel functional.
- Core workflows pass regression matrix.

## Milestone D — Public Release

**Goal:** production-ready desktop product.

Exit criteria:
- Stable update + rollback flow.
- Migration tooling for legacy project states.
- Security hardening baseline complete.
- Documentation/support playbook complete.

---

## 16) Migration path from current PARSE

## Stream 1 — Runtime and startup alignment

- Replace legacy launch assumptions with desktop-managed startup.
- Ensure backend can run from explicit project root (not implicit CWD).

## Stream 2 — Data model alignment

- Make annotation APIs canonical across Annotate + Compare.
- Ensure project creation/saving endpoints are consistent and implemented.

## Stream 3 — Frontend unification path

- Compare already uses modular JS + API path.
- Annotate (`parse.html`) currently remains legacy monolith/localStorage-heavy.
- Plan migration so Annotate uses shared module/data contracts incrementally.

## Stream 4 — Packaging and dependencies

- Add dependency manifests and lockfiles.
- Define packaged runtime + model distribution flows.

---

## 17) Biggest portability blockers identified (current codebase)

1. **Legacy launcher mismatch**
   - `start_parse.sh` and `Start Review Tool.bat` still reference `python/thesis_server.py` and `review_tool_dev.html` (legacy paths), not current server/UI entrypoints.

2. **Annotate mode is still monolithic/localStorage-first**
   - `parse.html` contains large inline app logic and localStorage persistence patterns rather than fully sharing the modular API-driven architecture.

3. **Project API contract mismatch**
   - Frontend modules call `/api/project` and `/project.json` save paths, but backend currently does not expose `/api/project` write route.

4. **Compute endpoint expectation mismatch**
   - Frontend expects offset/spectrogram compute routes; backend currently supports cognate compute flow only.

5. **No formal dependency lock/packaging manifests**
   - Python dependency footprint is non-trivial (audio, STT, NLP, optional providers), but there is no release-grade manifest/lockfile strategy in repo yet.

6. **Security defaults not desktop-hardened**
   - Backend defaults include `0.0.0.0` host and permissive CORS, which is unsafe for packaged desktop defaults.

7. **External CDN dependency in core UI**
   - `parse.html`/`compare.html` currently load WaveSurfer from `unpkg` CDN, which is fragile/offline-unfriendly for desktop packaging.

8. **Residual hardcoded platform paths in scripts/docs**
   - Legacy scripts/docs include machine-specific paths and Windows-specific assumptions that need explicit desktop compatibility policy.

---

## 18) Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Runtime packaging complexity (Python + heavy libs) | Delays beta/public | Stage rollout: system Python (alpha) → managed runtime (beta) |
| STT/model size and download friction | Poor first-run UX | Model manager with optional packs + resumable downloads |
| Annotate/Compare architecture divergence | Higher maintenance cost | Incremental annotate migration plan with compatibility adapters |
| Update-induced project breakage | Data loss/trust damage | Versioned migrations + backups + rollback |
| Localhost attack surface | Security risk | loopback-only bind, token auth, strict CORS/CSP |

---

## 19) Concrete recommended next tasks (buildable sequence)

## Phase 0 — Foundation contracts (no disruptive rewrites)

1. **Define desktop bootstrap contract**
   - Add backend startup flags spec (`project_root`, host/port, auth token, user-data root).
2. **Define project API write contract**
   - Formalize create/read/update endpoints for `project.json` lifecycle.
3. **Define compute capability matrix**
   - Explicitly document which `/api/compute/*` routes are implemented vs planned.

## Phase 1 — Desktop shell spike

4. Create `desktop/` shell prototype with Electron main + preload.
5. Spawn existing backend and load Compare mode in desktop window.
6. Add startup health check, backend logs, and graceful shutdown.

## Phase 2 — Packaging viability

7. Introduce Python dependency manifest/lock strategy and CI smoke install for Windows/macOS.
8. Vendor frontend third-party JS needed for offline packaged builds (remove mandatory CDN dependency).
9. Harden default backend bind/CORS/token behavior for desktop runtime.

## Phase 3 — Product-level polish

10. Implement settings UI for storage/model/performance/update controls.
11. Implement updater channels (`alpha` first).
12. Add migration/backups and regression checklist gating.

---

## 20) Decision log (update as decisions solidify)

| Date | Decision | Status |
|---|---|---|
| 2026-03-27 | Desktop direction = Electron shell + local Python backend | **Accepted (planning)** |
| 2026-03-27 | Boundary preference = localhost HTTP for core API, IPC only for native shell ops | **Accepted (planning)** |
| 2026-03-27 | This document is canonical living desktop plan | **Accepted** |

---

## 21) Open questions

1. Final Python runtime distribution approach for public release (embedded vs managed install-at-first-run).
2. Exact model bundles shipped by default vs downloaded on demand.
3. Whether to support Linux as official target in 1.x timeline.
4. Whether Annotate modular migration is required before beta or can continue behind compatibility layer.
5. Update backend service choice and signing/notarization infrastructure timeline.

---

## 22) Maintenance rule

When any of the following changes, update this file in the same PR:
- architecture boundary decisions,
- packaging/runtime decisions,
- release gate criteria,
- security default policy,
- milestone readiness definitions.
