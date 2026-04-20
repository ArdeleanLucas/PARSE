# PARSE Repository State Cleanup and Architecture Unification Plan

> **For Hermes:** Execute from the lowercase clone `/home/lucas/gh/ardeleanlucas/parse`. Do **not** merge to `main` directly. Open PRs; **Lucas must merge them**.

**Goal:** Finish the React cutover by deleting the vanilla-JS legacy surface and making the Python server serve the React build — in a scoped, reversible PR that can only run once Lucas authorizes destructive cleanup.

Phases 0–4 (preflight, canonicalization, non-destructive messaging, deferred-validation maintenance) and Phase 6 (post-merge branch pruning) are no longer active execution work; see the Stage 1 archive under `docs/archive/` for their history. This doc is now the Phase 5 slice only.

---

## Phase 5 — Legacy removal and Python-served React build

### Objective

Make PARSE expose only the React SPA at runtime and remove every vanilla-JS entrypoint from the repo. Aligned with Stage 3 of the 2026-04-20 docs audit.

### Gating note

This slice was formerly labeled "C7". Per `AGENTS.md` § Deferred Validation Backlog, C5 (LingPy TSV export verification) and C6 (full Annotate/Compare browser regression) are **not hard gates** for this PR. They stay on the deferred-validation list and are run once onboarding/import testing is usable enough for them to be meaningful. Phase 5 still requires a scoped PR, rollback notes, and Lucas-review-before-merge.

---

### Task 5.1 — Decide build artifact strategy for Python-served frontend

**Objective:** Specify exactly what the Python server serves after legacy removal.

**Files:** `README.md`, `python/server.py`, startup/build docs.

**Decision:**
- `npm run build` produces `dist/`.
- Python server serves the built React app from `dist/` for production-like / local-server usage.
- Vite `:5173` remains dev-only.

**Verification:** decision is documented in the same PR as the cleanup, before any file deletion.

**Merge:** PR required; Lucas merges.

---

### Task 5.2 — Remove legacy frontend files and switch canonical serving

**Objective:** Delete the no-longer-authoritative legacy UI and make the Python server serve the React build.

**Files:**
- Delete: `parse.html`, `compare.html`, `review_tool_dev.html`, `js/`.
- Delete: `forceSpaCompareRoute` plugin from `vite.config.ts` (only existed to redirect around `compare.html`).
- Modify: `python/server.py` to serve `dist/` for non-API routes.

**Preconditions:**
- Lucas has authorized destructive cleanup for this PR.
- Rollback point recorded in `docs/archive/plans/repo-cleanup-preflight.md`.
- Onboarding/import flow is usable enough that cleanup scope is grounded in real behavior rather than speculation.

**Acceptance criteria:**
- `npm run build` produces `dist/index.html` + required assets.
- Python server serves the built frontend for non-API routes.
- `GET /` returns the React app shell.
- `GET /compare` returns the React app shell via SPA fallback.
- `/api/*` routes still return JSON as before.
- Audio/static behavior needed by existing thesis workflows still works.
- No remaining references to `parse.html` / `compare.html` in source, launchers, or docs outside `docs/archive/`.

**Merge:** destructive — Lucas authorizes and merges.

---

### Task 5.3 — Remove remaining legacy references from docs and launchers

**Objective:** Finish cleanup so docs match reality on the same architecture cutover.

**Files:** `README.md`, `AGENTS.md`, launcher scripts (`start_parse.sh`, `Start Review Tool.bat`, `run-parse.sh`), relevant docs under `docs/` (not `docs/archive/`).

**Verification:**
- No user-facing doc implies `parse.html` / `compare.html` are the primary interface.
- No launcher still assumes legacy HTML entrypoints are canonical; launchers either boot the React SPA (via `python/server.py` + `dist/`) or are deleted.

**Merge:** PR required; Lucas merges.

---

## Exit criteria (Phase 5 overall)

- `rg -l 'parse\.html\|compare\.html\|review_tool_dev\.html\|^js/' -- . ':!docs/archive'` returns no hits.
- `npm run build && python/server.py` serves the React SPA on `127.0.0.1:8766` with `/api/*` still returning JSON.
- `AGENTS.md` Client/Server Contract Surface table still matches the live routes after the cutover.
