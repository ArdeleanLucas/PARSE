# PARSE Desktop Product Architecture (Living Plan)

> **UN-ARCHIVED 2026-07-08** — Option 3 (desktop platform pivot) was revived by Lucas decision **2026-07-04** (see AGENTS.md "Scope: Desktop (Option 3) REVIVED 2026-07-04", and the "Desktop / installable product" section in `CLAUDE.md`). This document was un-archived and reconciled against current code on 2026-07-08. The goal is a downloadable, installable desktop app — macOS first, then Windows — that a fieldwork linguist can install and use without today's terminal / Linux-WSL launcher. The existing React SPA + Python backend stay working throughout; desktop packaging wraps them, it does not replace them.
>
> **Last updated:** 2026-07-08
> **Status:** Active living plan (revived)
> **Scope:** Local desktop product foundation for macOS + Windows (Electron shell + frozen local Python engine)
>
> **2026-07-08 reconciliation note:** this plan was refreshed against the current codebase after ~4 months archived. Corrections from that pass: the offset/spectrogram compute routes are now **implemented** (`/api/spectrogram`, `/api/offset/detect`, `/api/offset/detect-from-pair`, `/api/offset/apply`), so §17 blocker #4 is resolved; the project-lifecycle gap is reframed (neither frontend nor backend exposes a project open/create flow today — the root is bound to `PARSE_WORKSPACE_ROOT` at launcher time). The remaining genuine blockers are runtime/dependency packaging, security defaults, the packaging pipeline itself, and the project-lifecycle contract.

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
| - app lifecycle           +------->| - static UI serving (dist/)          |
| - window creation         |        | - /api/* endpoints                   |
| - auto-update             |        | - job queue (stt/compute/export)     |
| - settings persistence    |        | - project IO + annotation IO         |
| - secure preload bridge   |        | - model orchestration                |
+-------------+-------------+        +------------------+-------------------+
              |                                            ^
              | loads http://127.0.0.1:<ephemeral_port>   |
              v                                            |
+---------------------------+                              |
| Renderer (PARSE UI)       |--- local HTTP API ----------+
| - React SPA (src/)        |
| - Tailwind + lucide-react |
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

**Decision (2026-07-08): freeze the backend per platform.** The backend and its heavy stack (`torch`, `torchaudio`, `transformers`, `faster-whisper`/ctranslate2, `silero-vad`, `phonemizer`) are packaged into a self-contained per-platform runtime (PyInstaller or Nuitka) against a pinned lockfile. A normal user never installs Python or runs `pip`. This costs a larger installer (order 1–3 GB once torch is included) but delivers true install-and-go, fully offline, which is the product goal for non-technical fieldwork users.

## 8.1 Target strategy by milestone

### Alpha (internal spike)
- System Python is acceptable **only** for the Gate A shell/lifecycle spike, to move fast.
- Desktop preflight checks required at startup.

### Beta
- Frozen per-OS/arch runtime is the deliverable (no system Python dependency).
- Lockfile + wheelhouse drive a reproducible freeze; offline-capable.

### Public
- Frozen runtime with deterministic dependency set, signed and notarized.
- No external Python requirement for any user.

## 8.2 Runtime management requirements

1. Runtime version pinned to **Python 3.10–3.12** (the range `python/requirements.txt` currently supports). Python 3.13+ is blocked until `python/server.py` stops importing the removed `cgi` module; that removal is a prerequisite for pinning a newer runtime.
2. Dependency installation deterministic (lockfile + wheelhouse). `python/requirements.txt` today uses floor pins (`>=`) with no lockfile — producing a release-grade lock is a Gate B prerequisite (see §9.1 and the readiness checklist B2).
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

## 9.2 Model strategy — bundled baseline + plug-and-play registry

**Decision (2026-07-08):**

- **Bundle as standard:** a general STT model (Whisper via `faster-whisper`) and the wav2vec2 IPA/alignment model. These ship in the installer so a fresh install can transcribe and produce IPA fully offline on first run.
- **Do not bundle any orthography (ORTH) model.** ORTH is inherently language-specific — there is no sensible default. `config/phonetic_rules.json` / SK presets ship as named presets, not defaults (this dovetails with the Beta linguistic-portability lane, checklist B6).
- **Plug-and-play models are a first-class design goal, not a nice-to-have.** A survey linguist working on a language PARSE has never seen must be able to obtain a model (for example `razhan/whisper-base-sdh` for Southern Kurdish) and "plug it in" per project/language without editing code or config files by hand. This needs deliberate design — see §9.4.

## 9.3 Model manifest and cache

- Maintain a **model manifest** (name, version, checksum, size, license, min runtime, task type STT/ORTH/IPA, and `(language, script)` applicability).
- User-selectable model cache location (default in the app user-data `models/` dir).
- Download/import manager with checksum verification and a clear fallback when a preferred model is unavailable.

## 9.4 Plug-and-play model design (open design task)

The goal: a linguist finds a model and installs it into PARSE the way they install a font or a Praat plugin — no terminal.

Design surface to specify before Beta:

1. **A model package contract** — what a "pluggable PARSE model" is on disk (the model artifact + a manifest entry declaring task, `(language, script)`, runtime, license, checksum). CT2-compatible artifacts for the faster-whisper path; do **not** depend on ad-hoc local HF cache structure.
2. **An install path** — "Add model…" in Settings > Models that accepts a local file/folder (offline field use) and, optionally, a curated download source. Verify checksum, register in the manifest, surface license.
3. **Per-project binding** — a project selects which STT/ORTH/IPA model it uses; selection is not hardcoded (see the Beta linguistic-portability lane, checklist B6 — "STT model is selected per project, not hardcoded to `razhan/whisper-base-sdh`").
4. **Discoverability** — a lightweight, community-extensible catalog of known models per language so survey linguists have a starting point, without PARSE having to bundle or endorse every one.

This subsection is the anchor for that design work; it is intentionally not yet a finished spec.

## 9.5 Local AI + MCP tool surface (offline)

**Decision (2026-07-08): the offline desktop build ships an MCP server that a local AI model can drive.** PARSE's ~67-tool surface is already exposed two ways in the current codebase, and both carry into the frozen desktop app:

- **stdio MCP server** — `python/adapters/mcp_adapter.py` (`main()` → `run_stdio_async()`). This is the standard transport a local MCP client/agent spawns as a subprocess. It must be reachable in the frozen build without system Python — expose it as an explicit entrypoint of the packaged binary (e.g. a `--mcp-stdio` subcommand) or a second bundled launcher, so a local MCP client can spawn it.
- **loopback HTTP MCP bridge** — `/api/mcp/exposure`, `/api/mcp/tools`, `/api/mcp/tools/{toolName}` on the backend HTTP server. Because the frozen backend already runs this server, any local process (including a local agent) can call the tools over `127.0.0.1` for free.

A local LLM path already exists: `OllamaProvider` (`python/ai/providers/ollama.py`, `http://localhost:11434`). So a fully-offline loop — local model ↔ PARSE MCP tools, entirely on the machine — is coherent today at the code level.

Design points to settle before Beta:

1. **Security interaction.** Desktop hardening adds a renderer↔backend session token and loopback-only bind (§14). That hardening must not lock out a legitimate local MCP client. Define how a local agent authenticates to the HTTP MCP bridge (e.g. a readable local token file in user-data, or a scoped localhost allowance for the MCP bridge). The stdio adapter is process-spawned and sidesteps the HTTP token question.
2. **Frozen stdio entrypoint.** Confirm the packaged app can launch the stdio adapter as a child process from a local MCP client config with no system Python.
3. **Bundling a local model runtime is a separate, optional decision.** PARSE talks to an Ollama instance if one is present; whether the installer also bundles/installs a local model runtime for turnkey offline AI is a scope question tracked separately. The MCP *server* (PARSE's tools) is available regardless of which model, if any, is installed.

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

### Milestone policy

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
- React routes or the Python-served built UI open from the desktop shell.
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

## Stream 3 — Frontend unification path ✅ complete

Annotate + Compare are unified in `src/ParseUI.tsx` (React SPA), sharing stores, hooks, and the typed API client. Stage 3 landed in PR #58, removing `js/`, `parse.html`, `compare.html`, `review_tool_dev.html`, and the legacy launchers, so the React SPA is now the sole frontend.

## Stream 4 — Packaging and dependencies

- Add dependency manifests and lockfiles.
- Define packaged runtime + model distribution flows.

---

## 17) Biggest portability blockers identified (current codebase)

1. ~~Legacy launcher mismatch~~ — **resolved.** Stage 3 / PR #58 removed the obsolete shell scripts and review-page entrypoint from the primary product flow.

2. ~~Annotate mode is still monolithic/localStorage-first~~ — **resolved as a portability blocker.** Annotate + Compare now live in the unified React shell with shared Zustand stores; remaining workflow hardening is follow-up polish rather than a legacy-architecture blocker.

3. **No project-lifecycle contract or UI** (reframed 2026-07-08)
   - There is no `/api/project` create/open/recent route, and no open/create/recent-project UI in `src/`. The project root is bound to `PARSE_WORKSPACE_ROOT` at launcher time. A desktop app needs a UI-driven open/create flow and a backend that can switch project roots at runtime. (The older "frontend calls `/api/project` but backend doesn't expose it" framing is itself stale — neither side has it now.) `project.json` is written today only as a side effect of speaker registration (`python/server_routes/media.py`).

4. ~~Compute endpoint expectation mismatch~~ — **resolved (2026-07-08).** `/api/spectrogram`, `/api/offset/detect`, `/api/offset/detect-from-pair`, and `/api/offset/apply` are all implemented in the current backend.

5. **No formal dependency lock/packaging manifests**
   - Python dependency footprint is non-trivial (audio, STT, NLP, optional providers), but there is no release-grade manifest/lockfile strategy in repo yet.

6. **Security defaults not desktop-hardened**
   - Backend defaults include `0.0.0.0` host and permissive CORS, which is unsafe for packaged desktop defaults.

7. ~~External CDN dependency in core UI~~ — **resolved.** React SPA bundles dependencies via Vite; `rg unpkg src/` returns zero hits, and the legacy HTML shells that depended on CDN assets were removed in Stage 3 / PR #58.

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

### Staged build sequence (2026-07-08 revival, macOS first → Windows next)

Each stage gates on both its Gate A/B/C criteria (see the readiness checklist) and this repo's test suite. The existing web/Python app keeps working throughout — all desktop hardening sits behind a desktop-runtime flag so the browser/Vite dev flow is untouched.

- **Stage 0 — Refresh the plan (docs only).** This document + the readiness checklist + `desktop/README.md`, un-archived and reconciled. *(This stage.)*
- **Stage 1 — Gate A shell + lifecycle spike (macOS).** Desktop-runtime backend hardening (loopback default, no wildcard CORS, per-session renderer↔backend token), ephemeral port + readiness handshake, Electron supervises the backend process (spawn → health → restart → clean shutdown).
- **Stage 2 — Gate A project lifecycle.** `/api/project` open/create/recent + a front-end open/create screen; backend accepts a project root at runtime.
- **Stage 3 — Gate B packaging (macOS).** Dependency lockfile + wheelhouse; frozen per-platform runtime (§8); electron-builder DMG/zip for arm64; ffmpeg/ffprobe policy; CPU-only default with GPU auto-fallback; bundled Whisper + wav2vec2 and the plug-and-play model install path (§9.4). Install-test the unsigned build.
- **Stage 4 — Gate C (macOS).** Code signing + notarization (Lucas's identity — a required pause point), update channel, migration/backup, QA smoke matrix.
- **Then Windows.** Replay Stages 3–4 with an NSIS installer, win-x64, ffmpeg bundling, and signing.

## Foundation contracts (no disruptive rewrites)

1. **Define desktop bootstrap contract**
   - Add backend startup flags spec (`project_root`, host/port, auth token, user-data root).
2. **Define project API write contract**
   - Formalize create/read/update endpoints for `project.json` lifecycle.
3. **Define compute capability matrix**
   - Explicitly document which `/api/compute/*` routes are implemented vs planned.

## Desktop shell spike

4. Create `desktop/` shell prototype with Electron main + preload.
5. Spawn existing backend and load Compare mode in desktop window.
6. Add startup health check, backend logs, and graceful shutdown.

## Packaging viability

7. Introduce Python dependency manifest/lock strategy and CI smoke install for Windows/macOS.
8. Vendor frontend third-party JS needed for offline packaged builds (remove mandatory CDN dependency).
9. Harden default backend bind/CORS/token behavior for desktop runtime.

## Product-level polish

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
| 2026-07-08 | Option 3 desktop direction revived; macOS first, then Windows | **Accepted (revived)** |
| 2026-07-08 | Python runtime packaging = freeze per platform (PyInstaller/Nuitka) against a pinned lockfile; no user Python | **Accepted** |
| 2026-07-08 | Ship Whisper (STT) + wav2vec2 (IPA) as standard bundled models; ship no ORTH model; make models plug-and-play per project/language (§9.4) | **Accepted** |
| 2026-07-08 | Offset/spectrogram compute routes confirmed implemented; §17 blocker #4 closed | **Verified** |
| 2026-07-08 | Offline desktop build ships an MCP server (stdio adapter + loopback HTTP bridge) a local AI model can drive; local-LLM path already exists via OllamaProvider (§9.5) | **Accepted** |

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

---

## Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-04-20 | Remove all vanilla JS (`js/`, `parse.html`, `compare.html`, `review_tool_dev.html`, legacy launchers) — React SPA becomes the sole frontend | Annotate/Compare divergence and CDN dependency were already resolved by the unified React shell; PR #58 completed the runtime cutover and removed the remaining packaging/offline/operator-confusion risks from the legacy frontend surface. |
| 2026-04-20 | Speaker onboarding requires explicit xAI/OpenAI provider selection at import time | No implicit default; per-provider chat runtime already validated. Ollama/offline deferred until a real offline-field requirement reappears. |
