# PARSE Repository State Cleanup and Architecture Unification Plan

> **Historical completion record (2026-04-21):** the legacy-removal slice described here is closed — Stage 3 landed in PR #58. Keep this file as the execution record for that cutover, not as an open runbook. For current PARSE repo policy, branch rules, and validation gates, use `AGENTS.md`.

**Historical goal at capture time:** Finish the React cutover by deleting the vanilla-JS legacy surface and making the Python server serve the React build — in a scoped, reversible PR that could only run once Lucas authorized destructive cleanup.

Earlier prep steps (preflight, canonicalization, non-destructive messaging, deferred-validation maintenance) and later post-merge branch pruning are no longer active execution work; see the Stage 1 archive under `docs/archive/` for their history. This doc is now the legacy-removal slice only.

---

## Legacy removal and Python-served React build ✅ complete on PR #58

### Objective

Make PARSE expose only the React SPA at runtime and remove every vanilla-JS entrypoint from the repo. Aligned with Stage 3 of the 2026-04-20 docs audit.

### Gating note

This slice was formerly labeled "C7". Per `AGENTS.md` § Deferred Validation Backlog, C5 (LingPy TSV export verification) and C6 (full Annotate/Compare browser regression) are **not hard gates** for this PR. They stay on the deferred-validation list and are run once onboarding/import testing is usable enough for them to be meaningful. The slice still requires a scoped PR, rollback notes, and Lucas-review-before-merge.

---

### Task 5.1 — Decide build artifact strategy for Python-served frontend ✅ done

**Objective:** Specify exactly what the Python server serves after legacy removal.

**Files:** `README.md`, `python/server.py`, startup/build docs.

**Decision:**
- `npm run build` produces `dist/`.
- Python server serves the built React app from `dist/` for production-like / local-server usage.
- Vite `:5173` remains dev-only.

**Verification:** ✅ Documented in PR #58 alongside the cleanup and runtime cutover.

**Merge:** PR required; Lucas merges.

---

### Task 5.2 — Remove legacy frontend files and switch canonical serving ✅ done

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
- [x] `npm run build` produces `dist/index.html` + required assets.
- [x] Python server serves the built frontend for non-API routes.
- [x] `GET /` returns the React app shell.
- [x] `GET /compare` returns the React app shell via SPA fallback.
- [x] `/api/*` routes still return JSON as before.
- [x] Audio/static behavior needed by existing thesis workflows still works.
- [x] No remaining references to the removed HTML entrypoints remain in source, launchers, or docs outside `docs/archive/`.

**Completion note:** Completed in PR #58.

**Merge:** destructive — Lucas authorizes and merges.

---

### Task 5.3 — Remove remaining legacy references from docs and launchers ✅ done

**Objective:** Finish cleanup so docs match reality on the same architecture cutover.

**Files:** `README.md`, `AGENTS.md`, launcher scripts (`start_parse.sh`, `Start Review Tool.bat`, `run-parse.sh`), relevant docs under `docs/` (not `docs/archive/`).

**Verification:**
- [x] No user-facing doc implies removed HTML entrypoints are the primary interface.
- [x] No launcher still assumes legacy HTML entrypoints are canonical; the obsolete launchers were deleted in PR #58.

**Completion note:** Completed in PR #58.

**Merge:** PR required; Lucas merges.

---

## Exit criteria (overall)

- [x] `rg -l 'parse\.html\|compare\.html\|review_tool_dev\.html\|^js/' -- . ':!docs/archive'` returns no hits.
- [x] `npm run build && python/server.py` serves the React SPA on `127.0.0.1:8766` with `/api/*` still returning JSON.
- [x] `AGENTS.md` Client/Server Contract Surface table still matches the live routes after the cutover.

**Status:** Complete via PR #58.
