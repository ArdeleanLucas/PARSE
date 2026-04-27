# PARSE Desktop Distribution Readiness Checklist

This checklist is the release gate companion to:
- `docs/archive/desktop_product_architecture.md` (historical architecture reference; Option 3 is cancelled)
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

- **Current target milestone:** Pre-implementation planning
- **Overall readiness:** Not started
- **Blocker count:** TBD

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

- [ ] Managed Python runtime strategy implemented (no required manual Python install).
- [ ] Deterministic dependency set documented (manifest/lock).
- [ ] Runtime preflight checks surface missing optional dependencies clearly.
- [ ] ffmpeg/ffprobe availability policy is implemented and documented.

## B3) Data/model management

- [ ] Model cache location configurable.
- [ ] Model download/install flow includes integrity checks.
- [ ] CPU-only mode works without GPU dependencies.
- [ ] GPU detection + automatic fallback to CPU implemented.

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

- [ ] Frontend/Backend project save contract mismatch (`/api/project` expectations vs implementation).
- [ ] Compute endpoint mismatch for offset/spectrogram flows.
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
