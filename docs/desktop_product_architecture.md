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
  models/               (user model root; each model is <id>/manifest.json + files — see §9.3)
    <id>/
      manifest.json
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

## 9.2 Model strategy — hybrid delivery + plug-and-play registry

**Decision (2026-07-09, supersedes the 2026-07-08 "bundle both models" baseline):** delivery is **hybrid** — bundle only the always-needed acoustic core, and deliver every other model (including the standard STT model) through one plug-in pipeline. There is no special-cased hardcoded STT default; "the standard STT model" is simply the first model-pack the registry installs. This unifies "the shipped default" and "a user plug-in" into a single mechanism.

Delivery rules:

- **Bundle one model only — the IPA acoustic core.** The wav2vec2 IPA/alignment model (as one example, `facebook/wav2vec2-xlsr-53-espeak-cv-ft`) ships read-only inside the installer/DMG under app Resources. It is the always-needed acoustic core, so bundling it keeps the app usable offline for IPA immediately on first run.
- **Do not bake the standard STT model into the installer.** The standard STT model (as one example, a Whisper `small` multilingual model, ~460 MB) is fetched on first run — but it is delivered *through the same plug-in pipeline as any other model*. It is just the first model-pack the registry installs; there is no hardcoded STT default path. See §9.4 for the first-run fetch and the resolution precedence.
- **Do not bundle any orthography (ORTH) model.** ORTH is inherently language-specific — there is no sensible default. Users plug an ORTH model in per project/language if they want one. `config/phonetic_rules.json` / SK presets ship as named presets, not defaults (this dovetails with the Beta linguistic-portability lane, checklist B6).
- **Plug-and-play models are a first-class design goal, not a nice-to-have.** A survey linguist working on a language PARSE has never seen must be able to obtain a model (for example `razhan/whisper-base-sdh` for Southern Kurdish) and "plug it in" per project/language without editing code or config files by hand. §9.4 specifies that mechanism as the plan-of-record.

## 9.3 On-disk layout — two model roots

The registry reads from **two roots**, both of which the Electron shell communicates to the backend at launch. This reuses the existing bundled-resource *discovery* pattern (the ffmpeg `PARSE_BUNDLED_BIN` env var, which `python/shared/ffmpeg_discovery.py` reads and skips when unset; see checklist B2). Note the discovery side is the only part that exists today: the backend already knows how to read and skip these env vars, but nothing in `desktop/` sets `PARSE_BUNDLED_BIN` or `PARSE_BUNDLED_MODELS` yet — wiring the shell to set them is part of the pending packaging work (the "bundle IPA into Resources" increment in checklist gate B).

1. **Bundled root (read-only).** The app Resources `models/` directory, discoverable via a new env var the Electron shell sets at launch — `PARSE_BUNDLED_MODELS=<resourcesPath>/models`. Unset in dev → the bundled root is simply skipped (exactly how `PARSE_BUNDLED_BIN` behaves today). Bundled models are read-only; the Models manager cannot remove them.
2. **User root (writable).** `PARSE_USER_DATA/models/`. `PARSE_USER_DATA` is already passed from the Electron shell to the backend (see `desktop/backend-supervisor.js`, which sets `PARSE_USER_DATA: this._options.userDataRoot`). This is where every installed and downloaded model lands.

Each installed model — in either root — is a subdirectory named by its stable `id`:

```text
<root>/models/
  <id>/
    manifest.json      (the model-pack manifest, schema below)
    <model files>      (or an entrypoint subdir the manifest points at)
```

The default cache location is the user root above; it remains user-selectable via Settings > Storage as today.

## 9.3.1 Model-pack + manifest contract (schema_version 1)

A **PARSE model-pack** is a zip whose root contains `manifest.json` plus the model files (or an entrypoint subdirectory). Installing a pack normalizes it to `<user root>/models/<id>/`. The manifest is the single source of truth for how the registry resolves and loads a model:

```json
{
  "schema_version": 1,
  "id": "whisper-small",                      // stable unique slug = install dir name
  "name": "Whisper small (multilingual)",     // display name
  "stage": "stt",                             // one of: "stt" | "ipa" | "ortho"
  "format": "faster-whisper-ct2",             // "faster-whisper-ct2" (CTranslate2 dir for faster-whisper) | "hf-transformers" (HF from_pretrained dir)
  "engine": "faster-whisper",                 // informational: "faster-whisper" | "wav2vec2" | "hf-whisper"
  "languages": ["*"],                         // ["*"] = any, or a list of language codes
  "entrypoint": ".",                          // path within the model dir passed to the loader (WhisperModel(dir) / from_pretrained(dir))
  "version": "1.0.0",
  "source": { "type": "bundled|user|hf", "ref": "<hf repo id | pack filename | ''>" },
  "size_bytes": 460000000                     // optional, for UI display
}
```

Field semantics:

- **`id`** — stable unique slug; it is also the install directory name, so it must be filesystem-safe and unique across both roots.
- **`stage`** — which pipeline stage the model serves: `stt`, `ipa`, or `ortho`. Stage→model resolution (§9.4) keys off this.
- **`format`** — how the loader consumes the model dir. `faster-whisper-ct2` is a CTranslate2 model directory loaded by faster-whisper; `hf-transformers` is a Hugging Face `from_pretrained` directory. `format` (how to load) is intentionally distinct from `engine` (informational label).
- **`entrypoint`** — a path *within* the model dir that the loader receives. It resolves to an absolute local directory that the loader consumes. `"."` means the model dir itself.
- **`languages`** — `["*"]` means the model applies to any language; otherwise a list of language codes used for display/filtering only (it does not override an explicit per-project binding).
- **`source`** — provenance for display and re-fetch: `bundled` (shipped in Resources), `user` (installed from an uploaded pack), or `hf` (downloaded from a Hugging Face repo id, recorded in `ref`).

### How a manifest maps to the existing loaders

The registry does not introduce a new loading path. Both existing loaders already accept **either** a local directory **or** a Hugging Face repo id, so a model-pack's `entrypoint` simply resolves to an absolute local directory the loader consumes:

- **STT and faster-whisper-format ORTH** — `WhisperModel(<entrypoint_dir>)` (faster-whisper over a CTranslate2 directory).
- **wav2vec2 IPA and HF-transformers ORTH** — `*.from_pretrained(<entrypoint_dir>)` (for example `Wav2Vec2ForCTC.from_pretrained(...)` in `python/ai/forced_align.py`, or the HF-Whisper ORTH provider).

So resolving a stage to a model means: look up the stage's model id, read its manifest, and hand the loader the absolute `entrypoint` directory. No loader change is required for the desktop registry; it feeds local directories into the paths that already exist.

## 9.4 Plug-and-play model design (decided — plan of record)

**Decided 2026-07-09.** The goal is unchanged: a linguist finds a model and installs it into PARSE the way they install a font or a Praat plugin — no terminal. This subsection is now the single source of truth for that mechanism; the sections below are the plan the implementation PRs build against, not open design questions.

The mechanism is one **desktop model registry** that scans the two roots of §9.3, reads each `manifest.json`, and answers two questions: *what models are installed?* and *which model serves this stage for this project?* The same registry delivers the standard STT model (§9.2) and any user plug-in — they differ only in `source`.

### 9.4.1 Install sources (two)

Both sources normalize to a directory under the user root — `PARSE_USER_DATA/models/<id>/` with a `manifest.json`:

1. **A model-pack zip** the user uploads or drops in. PARSE unpacks it, validates the manifest against schema_version 1, and stores it under the user root by its `id`.
2. **A Hugging Face repo id** the user pastes (for example `razhan/whisper-base-sdh`). PARSE downloads the repo, **wraps it with a generated manifest** (filling `id`, `stage`, `format`, `source.type = "hf"`, `source.ref = <repo id>`, `entrypoint = "."`), and stores it under the user root.

Because downloads and unpacks are slow, **install MUST be a job-tracked background operation** — return `202 + {jobId}` immediately and emit progress — per the AGENTS.md long-running-endpoint rule. The Models manager shows install progress from the job.

### 9.4.2 Stage → model resolution precedence

For a given pipeline stage (`stt` / `ipa` / `ortho`) the registry resolves a model in this order:

1. **Explicit per-project binding.** `project.json` carries a `models` mapping of stage → model `id`, e.g. `"models": { "stt": "whisper-small", "ipa": "wav2vec2-espeak", "ortho": "razhan-whisper-base-sdh" }`. If the stage has a binding, use that model id.
2. **The single installed model for that stage.** If exactly one model of that stage is installed (across both roots) and there is no explicit binding, use it.
3. **First-run fetch (STT only).** If the stage is `stt` and no STT model is installed, trigger the first-run fetch of the standard STT pack (§9.2) through the install pipeline above. This is the *only* stage with an implicit fetch, and it is not a hardcoded model path — it is the registry installing its first model-pack.
4. **Clear error otherwise.** If none of the above resolves (e.g. ORTH with no model installed and no binding), the stage errors clearly, naming the stage and pointing at Settings > Models — it does not silently pick a model or fall back to a hardcoded default.

### 9.4.3 Backward-compatibility guarantee (additive, desktop-oriented)

The registry is **purely additive**. When no models directory / registry entry exists for a stage — which is the case for the web product and for any non-desktop deployment — behavior is **exactly as today**: the stage loads from the existing `config` `model_path` / Hugging Face repo id, unchanged. The registry only takes over resolution when a desktop models root is present and has an entry for the stage. No existing config path is removed or rewritten; the desktop registry is a resolution layer that sits *in front of* the current behavior and defers to it whenever it has nothing to say.

### 9.4.4 Settings > Models manager (v1 UX)

A Settings panel that makes the registry usable without a terminal:

- **Installed-models list** — each row shows name, stage, size, a source badge (bundled vs user), and whether it is read-only (bundled) or removable (user).
- **Add control** — either upload a model-pack zip or paste a Hugging Face repo id. Either path kicks off the job-tracked install (§9.4.1) and shows install progress inline.
- **Remove** — user models only; bundled models are read-only and cannot be removed.
- **Per-project stage assignment** — dropdowns for STT / IPA / ORTH, each listing the installed models of that stage, writing the `project.json` `models` binding (§9.4.2, precedence step 1).
- **First-run** — if no STT model is installed, the panel prompts to download the standard STT pack, driving the first-run fetch (§9.4.2, step 3) through the same install job.

### 9.4.5 HTTP surface (to be implemented)

The registry is exposed over the loopback HTTP backend. These routes are the plan of record for the implementation PRs:

| Route | Purpose |
|---|---|
| `GET /api/models` | List installed models (both roots), with manifest fields for the manager. |
| `GET /api/models/{id}` | Detail for one model. |
| `POST /api/models/install` | Install a model. **202 + `{jobId}`**; accepts either a multipart model-pack upload or a JSON body `{hfRepoId, stage, format}`. Job-tracked (§9.4.1). |
| `DELETE /api/models/{id}` | Remove a model (user models only; bundled are read-only). |
| `GET /api/models/binding?project=<root>` | Read the per-project stage → model id binding. |
| `POST /api/models/binding` | Write the per-project stage → model id binding. |

When the matching `src/api/contracts/*` client helpers land, these routes MUST be added to the client/server contract table in `AGENTS.md` / `CLAUDE.md` (the "every new client helper must have a matching server route before merge" rule). `POST /api/models/install` follows the long-running-endpoint checklist: register the install `compute_type` at both dispatch sites in `python/server_routes/jobs.py`, emit `_set_compute_progress` as the download/unpack advances, and have the frontend consume it via `startCompute` / `pollCompute` — never a bare `apiFetch` against the start endpoint.

### 9.4.6 Discoverability (unchanged intent)

A lightweight, community-extensible catalog of known models per language remains a nice-to-have so survey linguists have a starting point, without PARSE bundling or endorsing every one. It is not required for v1: the paste-a-Hugging-Face-repo-id install source covers the "I already found a model" case, which is the primary field need.

**Build status (storage + API landed):** the model-registry read/resolve core (`python/ai/model_registry.py`) plus the write side (`python/ai/model_install.py` + `python/server_routes/models.py`) are in place: `POST /api/models/install` (job-tracked, pack-upload or HF download), `DELETE /api/models/{id}` (user models only), and `GET`/`POST /api/models/binding` (per-project stage→model binding persisted under the `project.json` `models` key). **Open follow-up (not yet built):** wiring the providers/aligner to auto-consult the per-project binding during stage resolution. `resolve_stage_model(stage, binding_id=...)` already accepts a binding id, but no provider passes the project's stored binding yet — a project's selection is stored and validated but not consulted at compute time. That resolution wiring is the next step, tracked separately from this storage+API landing.

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
