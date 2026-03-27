# PARSE Desktop Shell Scaffold (MC-247)

This directory is an **isolated Electron scaffold** for PARSE's desktop direction (Mac + Windows), while keeping the current web UI + Python backend workflow intact.

## Why this exists

- PARSE is moving toward a desktop product, but this wave is intentionally non-invasive.
- Everything in this step lives under `/desktop` only.
- No root build wiring, no changes to existing frontend/backend modules, and no migration risk for active development.

## What this scaffold can already do

1. Start a minimal Electron main process (`main.js`).
2. Open a local PARSE URL (default: `http://127.0.0.1:8766/parse.html`).
3. Use secure Electron defaults for a shell app:
   - `contextIsolation: true`
   - `sandbox: true`
   - `nodeIntegration: false`
   - preload bridge with limited IPC (`preload.js`)
4. Optionally sketch future backend orchestration:
   - if `PARSE_AUTO_BACKEND=1`, Electron will attempt to spawn the Python server command.
5. Provide a small dev launcher (`dev-launch.js`) for local runs with optional backend startup.

## Quick start (scaffold/dev only)

```bash
cd desktop
npm install
```

### A) If PARSE backend is already running

```bash
npm run start
```

### B) Start shell + sketch backend launch flow

```bash
npm run dev -- --with-backend
```

### C) Load a different entry point (example: Compare mode)

```bash
npm run dev -- --url http://127.0.0.1:8766/compare.html
```

## Environment variables

- `PARSE_APP_URL` — URL Electron should open.
- `PARSE_AUTO_BACKEND` — set to `1` to let Electron attempt backend launch.
- `PARSE_BACKEND_CMD` — backend command override (default: `python3 python/server.py`, Windows: `python python/server.py`).
- `PARSE_PROJECT_ROOT` — working directory for backend command (defaults to repo root).

## What is still missing before this is a real packaged app

- Embedded/managed Python runtime per platform (instead of relying on system Python).
- Robust backend lifecycle management (health checks, retries, readiness checks, clean shutdown guarantees).
- Packaging pipeline (installers for macOS + Windows, signing/notarization).
- Auto-update flow and release channels.
- Native desktop UX polish (menus, dialogs, file associations, deep links).
- Persistence/migration strategy for local desktop app state.

## Scope guardrails for this wave

- This is a shell scaffold, **not** a desktop migration.
- Existing PARSE web/Python stack remains the source of truth.
- Root repo build and existing app files remain untouched.
