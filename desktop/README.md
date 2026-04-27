> **ARCHIVED 2026-04-26:** desktop packaging is cancelled with Option 3. This directory is preserved as historical scaffolding only; do not extend it for active rebuild work.

# PARSE Desktop Shell Scaffold (MC-247)

This directory is an **isolated Electron scaffold** for PARSE's desktop direction (Mac + Windows), while keeping the current web UI + Python backend workflow intact.

## Why this exists

- PARSE is moving toward a desktop product, but this wave is intentionally non-invasive.
- Everything in this step lives under `/desktop` only.
- No root build wiring, no changes to existing frontend/backend modules, and no migration risk for active development.

## What this scaffold can already do

1. Start a minimal Electron main process (`main.js`).
2. Open a local PARSE URL.
   - Current React/Vite dev target (default): `http://127.0.0.1:5173/` or `http://127.0.0.1:5173/compare`
   - Optional Python-served built UI after `npm run build`: `http://127.0.0.1:8766/` or `http://127.0.0.1:8766/compare`
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

### A) Attach Electron to the current React/Vite UI

Start the PARSE backend (`python/server.py`, now a thin HTTP orchestrator with concrete route domains under `python/server_routes/`) and Vite (`npm run dev`) in the repo root first, then run:

```bash
npm run dev -- --url http://127.0.0.1:5173/
```

### B) Target the current React Compare route

If Vite is already running on `:5173`, you can target Compare directly:

```bash
npm run dev -- --url http://127.0.0.1:5173/compare
```

> `--with-backend` only sketches Python backend launch. It does **not** launch Vite, so the React UI still requires `npm run dev` in the repo root.

### C) Target the Python-served built UI

If you have already run `npm run build` in the repo root and want Electron to load the Python-served frontend shell:

```bash
npm run dev -- --url http://127.0.0.1:8766/
npm run dev -- --url http://127.0.0.1:8766/compare
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
