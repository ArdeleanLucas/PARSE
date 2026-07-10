# PARSE Desktop Distribution Readiness Checklist

This checklist is the release gate companion to:
- `docs/desktop_product_architecture.md` (the active living architecture plan; Option 3 revived 2026-07-08)
- `docs/plans/generalize-beyond-southern-kurdish.md` (linguistic portability work tied to the Beta gate)

Use this file to track practical readiness for shipping PARSE Desktop on macOS + Windows.

---

## How to use this checklist

1. Keep this file updated in the same PRs that change packaging/runtime/release behavior.
2. Check items only when objectively verified (not just “implemented”).
3. Add short evidence notes (PR number, test log, artifact link) under each section as needed.
4. Treat unchecked **must-pass** items as release blockers.

---

## Status snapshot (update per milestone)

- **Current target milestone:** Gate A — Internal Alpha (macOS), revived 2026-07-08
- **Overall readiness:** Plan refreshed; no packaging work started yet
- **Open blockers (2026-07-08):** frozen Python runtime + dependency lock; desktop-hardened security defaults (`0.0.0.0`/CORS today); packaging pipeline (no electron-builder/freeze config); project-lifecycle contract + UI. Offset/spectrogram compute-route mismatch is **resolved** (routes implemented).
- **Key decisions:** runtime = freeze per platform (PyInstaller/Nuitka); bundle Whisper + wav2vec2, no ORTH model, models plug-and-play per project (see architecture §9.2–§9.4).

---

## Gate A — Internal Alpha (must pass)

Goal: PARSE Desktop launches and runs core local workflow for internal team.

## A1) Bootstrap/runtime

- [ ] Electron shell starts and opens a window reliably.
- [ ] Backend process starts automatically from the shell (no manual terminal steps).
- [ ] Backend startup handshake is validated before renderer loads.
- [ ] Graceful shutdown of backend on app exit.
- [ ] Crash path shows actionable recovery dialog.

## A2) Project handling

- [ ] Open existing project folder flow works.
- [ ] Create new project flow works and persists `project.json`.
- [ ] Recent projects list works (open/remove/reopen).
- [ ] Invalid project folder shows clear validation errors.

## A3) Core workflows

- [ ] Annotate mode loads in desktop app.
- [ ] Compare mode loads in desktop app.
- [ ] Annotation read/write works for at least one test project.
- [ ] Enrichments read/write works for at least one test project.

## A4) Logging + diagnostics

- [ ] Main/renderer/backend logs are written to user-data logs directory.
- [ ] Diagnostic bundle export exists (minimum: logs + version info + env summary).

## A5) Security baseline (alpha minimum)

- [ ] Backend binds to loopback only in desktop runtime (`127.0.0.1`).
- [ ] Desktop runtime does not expose permissive wildcard CORS policy.
- [ ] Renderer cannot use Node globals directly (`nodeIntegration: false`, preload bridge only).

---

## Gate B — Closed Beta (must pass)

Goal: usable by external testers on macOS + Windows with managed runtime.

## B1) Packaging artifacts

- [ ] Windows installer artifact generated and install-tested.
- [ ] macOS app artifact generated and install-tested.
- [ ] Architecture builds validated for intended OS targets (e.g., win-x64, mac-arm64/mac-x64).

## B2) Python runtime/dependencies

- [ ] Frozen per-platform Python runtime implemented (PyInstaller/Nuitka; no required manual Python install). Pin inside Python 3.10–3.12 (3.13 blocked by the `cgi` import in `python/server.py`).
- [ ] Deterministic dependency set produced (lockfile + wheelhouse). Today `python/requirements.txt` is floor-pinned (`>=`) with no lock — this is a Gate B prerequisite.
- [ ] Runtime preflight checks surface missing optional dependencies clearly.
- [x] ffmpeg/ffprobe availability policy is implemented and documented. Resolver: `python/shared/ffmpeg_discovery.py` (`discover_ffmpeg` / `discover_ffprobe`, plus cached `cached_ffmpeg` / `cached_ffprobe` accessors). The server normalize route (`python/server_routes/media.py`), the peaks MP3 fallback (`python/peaks.py`), and the normalize CLI (`python/normalize_audio.py`) all go through the shared discovery policy, so a packaged app that bundles ffmpeg off-PATH works over HTTP, not just from the standalone CLI. Other standalone CLI utilities (`video_sync.py`, `video_clip_extract.py`, `export_review_data.py`, `batch_reextract.py`) still call bare `ffmpeg`/`ffprobe` and are a noted follow-up. Discovery order and env vars are documented in the "ffmpeg/ffprobe discovery policy" note below.

### ffmpeg/ffprobe discovery policy (B2 evidence)

`python/shared/ffmpeg_discovery.py` resolves `ffmpeg` (and `ffprobe`) by trying candidates in this order and returning the first that verifies via a `-version` probe:

1. **Explicit path argument** — a caller-supplied path (e.g. the `normalize_audio.py --ffmpeg` CLI flag). Highest priority; a set-but-invalid `--ffmpeg` fails fast rather than silently auto-discovering.
2. **`PARSE_FFMPEG` / `PARSE_FFPROBE`** override env vars (with the legacy `FFMPEG_PATH` honored below the new `PARSE_FFMPEG` var, for back-compat). Back-compat behavior delta: an invalid legacy `FFMPEG_PATH` now falls through silently to the next candidate — the old `normalize_audio` resolver printed a warning for a set-but-invalid `FFMPEG_PATH`; the shared policy does not.
3. **Bundled desktop location** — the `PARSE_BUNDLED_BIN` directory (reserved for a future bundling step; nothing sets it yet) and paths relative to a frozen executable (`sys._MEIPASS` / `sys.executable`'s dir). This makes discovery ready for a future packaging step that ships ffmpeg alongside the frozen backend; nothing is bundled today.
4. **`PATH`** via `shutil.which` (covers Homebrew / apt / system installs on macOS/Linux and Windows `PATH`).
5. **Common per-OS install locations** — macOS: `/opt/homebrew/bin`, `/usr/local/bin`; Linux: `/usr/bin`, `/usr/local/bin`; Windows: `%ProgramFiles%\ffmpeg\bin` plus the Chocolatey path (`C:\ProgramData\chocolatey\bin`) as one fallback among others, not the primary.

If nothing verifies, an actionable error names the override env vars and how to install ffmpeg. `ffprobe` additionally prefers a sibling next to a resolved `ffmpeg` before falling back to `PATH`/common locations. The module is stdlib-only so it stays importable in a frozen build and in hermetic tests (`python/test_ffmpeg_discovery.py`).

## B3) Data/model management

- [ ] Whisper (STT) and wav2vec2 (IPA) ship bundled so a fresh install transcribes and produces IPA offline. No ORTH model is bundled.
- [ ] Plug-and-play model install path implemented — a linguist can add a model (e.g. `razhan/whisper-base-sdh`) per project without editing code/config by hand (see architecture §9.4).
- [ ] Model cache location configurable.
- [ ] Model download/install flow includes integrity checks.
- [x] CPU-only mode works without GPU dependencies. Device resolution defaults to CPU when no CUDA is present: `resolve_compute_device(stage, config_device=, section_default="auto")` in `python/ai/device.py` maps `"auto"` → `"cuda"` only when `torch.cuda.is_available()`, else `"cpu"`. wav2vec2 IPA is CPU-safe through the same resolver (`python/ai/forced_align.py`, `resolve_compute_device("ipa", ...)`; torch on CPU needs no compute_type). faster-whisper `compute_type` is now device-aware: on a CPU-resolved device `float16` is coerced to `int8` before model load (`python/ai/providers/local_whisper.py`), because ctranslate2 supports `int8`/`int8_float32`/`int16`/`float32` on CPU but not `float16` (which would otherwise silently degrade to `float32` — slower, higher memory). Any other explicit CPU compute_type is honored; GPU keeps `float16`. This lets a frozen CPU-only build run STT/ORTH offline with a supported, low-memory compute type. Covered by `python/test_local_whisper_cpu_compute_type.py`.
- [x] GPU detection + automatic fallback to CPU implemented. `resolve_compute_device` falls back proactively (an explicit `"cuda"` request on a machine without CUDA resolves to `"cpu"` with a warning) and the faster-whisper loader falls back reactively (a CUDA runtime failure at model load retries `device="cpu"`, `compute_type="int8"`; `python/ai/providers/local_whisper.py`). GPU behavior is otherwise unchanged (`device` startswith `"cuda"` keeps `float16`).

## B4) Update infrastructure

- [ ] Update channel support in app (`alpha`/`beta`/`stable` at minimum routing level).
- [ ] “Check for updates” and apply-on-restart flow tested.
- [ ] Failed update path does not corrupt install.

## B5) Cross-platform behavior parity

- [ ] Project open/create/save behavior consistent on Windows and macOS.
- [ ] Path normalization and file permissions tested across both OSes.
- [ ] Long-running jobs (STT/compute/export) tested on both OSes.

## B6) Linguistic portability (Beta gate)

See `docs/plans/generalize-beyond-southern-kurdish.md` for the full work breakdown.

- [ ] No hardcoded `"sdh"` / `"ku"` / `"kur-Arab"` language defaults on server or compute paths.
- [ ] STT model is selected per project, not hardcoded to `razhan/whisper-base-sdh`.
- [ ] `config/phonetic_rules.json` ships empty; SK rules available as a named preset.
- [ ] Orthography→IPA conversion dispatches by `(language, script)` — no implicit SK-Arabic fallback.
- [ ] At least one non-SK language validated end-to-end through annotate + compare.

## B7) Security hardening for beta

- [ ] Session auth token between renderer and backend implemented.
- [ ] Navigation hardening blocks unexpected external page loads.
- [ ] IPC surface uses allowlisted channels only.
- [ ] No mandatory remote CDN dependency in packaged desktop build.
- [ ] Local MCP access preserved under hardening: PARSE's MCP tool surface (stdio adapter + loopback HTTP bridge) remains usable by a local AI model in the frozen build, and the session-token/loopback hardening does not lock out a legitimate local MCP client (see architecture §9.5).

---

## Gate C — Public Release (must pass)

Goal: stable, supportable desktop release for end users.

## C1) Release engineering and trust

- [ ] Code signing enabled for release artifacts.
- [ ] macOS notarization completed for release builds.
- [ ] Versioning policy defined (semver + channel behavior).
- [ ] Release notes generation and publishing process documented.

## C2) Migration and rollback safety

- [ ] Project/data schema migration framework implemented (versioned).
- [ ] Automatic pre-migration backups created.
- [ ] Rollback policy for failed migrations documented and tested.
- [ ] App update rollback path tested.

## C3) Performance and reliability

- [ ] Cold start time budget met on reference hardware.
- [ ] Memory ceiling monitored during long sessions.
- [ ] Large-audio workflow tested (multi-hour files).
- [ ] STT/compute queue behavior stable under repeated runs.

## C4) QA coverage

- [ ] Smoke tests for startup/project open/annotate/compare/export.
- [ ] API contract regression tests for desktop-critical endpoints.
- [ ] Installer upgrade path tested across at least two previous versions.
- [ ] Crash recovery scenarios tested (backend crash, renderer crash, interrupted update).

## C5) Documentation/support readiness

- [ ] End-user install guide (Windows + macOS).
- [ ] First-run setup guide (projects, models, providers).
- [ ] Troubleshooting guide (logs, diagnostics, common errors).
- [ ] Internal runbook for release/rollback/incidents.

---

## Cross-cutting implementation checklist

These items should be tracked continuously, not only at gate boundaries.

## D1) API and contract alignment

- [ ] Project create/update API route(s) are fully implemented and used consistently.
- [ ] Compute route expectations in frontend match backend implementation.
- [ ] Endpoint naming and payloads are documented in one canonical source.

## D2) Legacy compatibility cleanup

- [x] Legacy vanilla-JS entrypoints (`js/`, `parse.html`, `compare.html`, `review_tool_dev.html`) removed from the repo — completed in Stage 3 / PR #58.
- [x] Legacy launchers (`start_parse.sh`, `Start Review Tool.bat`) removed from the primary product flow in Stage 3 / PR #58.
- [ ] Legacy hardcoded machine paths removed from runtime-critical code paths.
- [x] Annotate + Compare persistence expectations are documented and converging — unified in `src/ParseUI.tsx` with shared Zustand stores.

## D3) Security and privacy

- [ ] Default runtime is local-first with no unintended network exposure.
- [ ] API key handling avoids plaintext leakage in logs.
- [ ] PII-sensitive logs are redacted/sanitized where appropriate.
- [ ] Export/share actions are explicit user actions (no silent exfiltration behavior).

## D4) Observability and supportability

- [ ] Structured log format/version tagged.
- [ ] Diagnostic bundle includes runtime versions + active settings snapshot.
- [ ] Error codes/messages are stable enough for support triage.

---

## Known current blockers to clear before beta/public

- [ ] No project-lifecycle contract or UI: no `/api/project` create/open/recent route and no open/create/recent-project UI; project root is bound to `PARSE_WORKSPACE_ROOT` at launcher time.
- [x] ~~Compute endpoint mismatch for offset/spectrogram flows~~ — resolved 2026-07-08; `/api/spectrogram` and the three `/api/offset/*` routes are implemented.
- [x] ~~Legacy vanilla-JS entrypoints still in the repo — Stage 3 of docs audit 2026-04-20.~~ Cleared in PR #58.
- [x] ~~Legacy launcher scripts (`start_parse.sh`, `Start Review Tool.bat`) still reference legacy paths — cleared in Stage 3.~~ Cleared in PR #58.
- [ ] Desktop security defaults not yet hardened (`0.0.0.0`/CORS policy in current backend defaults).
- [ ] No release-grade dependency lock/runtime packaging manifest in repo yet.
- [x] ~~Annotate mode still monolithic/localStorage-heavy~~ — resolved by the unified React shell (`src/ParseUI.tsx`).
- [x] ~~Packaged build still depends on remote CDN assets~~ — React SPA bundles via Vite; no `unpkg`/CDN hits in `src/`, and the vanilla-JS pages that depended on CDN assets were removed in PR #58.

---

## Sign-off template per gate

Use this at the bottom of release PRs.

```text
Gate: [A Internal Alpha | B Closed Beta | C Public]
Date:
Commit/Tag:
Build artifacts:
Test matrix summary:
Known deviations:
Go/No-go decision:
Approver(s):
```

---

## Maintenance rule

If architecture decisions, packaging behavior, or release gates change, update this checklist in the same PR as code changes.
