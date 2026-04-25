# parse-B.E. next task — backend job observability HTTP extraction

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Date:** 2026-04-25
**Owner:** parse-back-end
**Status:** queued / ready on current `origin/main`

## Goal

Start the new backend lane with a safe, behavior-preserving server refactor: extract the **generic job observability + worker-status HTTP handlers** out of `python/server.py` into a dedicated app-layer helper module, while preserving all current route behavior and tests.

## Why this is the right first parse-B.E. slice

- This lane is fully backend-only and does **not** overlap with parse-builder's current frontend shell work.
- Current rebuild `main` already contains the earlier backend extraction pattern:
  - PR #4 — backend HTTP helper slice (`request_helpers.py`, `response_helpers.py`)
  - PR #8 — external API HTTP handler slice (`external_api_handlers.py`)
- `python/server.py` is still large (**8897 lines**, verified on current rebuild `main`).
- The next coherent cluster still inline in `python/server.py` is the generic jobs/observability seam.
- Existing tests already lock down much of this behavior, making the slice safe to extract with TDD.

## Current grounded context

Verified on current rebuild `origin/main` before writing this prompt:

- Current `origin/main` tip: `bf497ee docs: add parse-builder stage2 offset workflow prompt (#9)`
- Recent rebuild history:
  - `bf497ee` — PR #9
  - `f812798` — PR #8
  - `f4fa47d` — PR #4
  - `7d17272` — PR #3
  - `d1bc2b6` — PR #1
- Current extracted backend helpers already exist under `python/app/http/`:
  - `request_helpers.py`
  - `response_helpers.py`
  - `external_api_handlers.py`
  - `static_paths.py`
- Relevant inline handler cluster still in `python/server.py`:
  - `_api_get_jobs()` — around **`6760-6784`**
  - `_api_get_job()` — around **`6786-6793`**
  - `_api_get_job_logs()` — around **`6795-6819`**
  - `_api_get_jobs_active()` — around **`6821-6824`**
  - `_api_get_job_error_logs()` — around **`6826-6871`**
  - `_api_get_worker_status()` — around **`6873-6908`**
- Existing integration/handler coverage already lives in:
  - `python/test_server_job_observability.py`
  - `python/test_external_api_surface.py`
- Existing behavior note:
  - `_api_get_jobs()` and `_api_get_job_logs()` are still manually parsing query strings with `urlparse` / `unquote`, despite the earlier extracted request-helper seam already existing.

## Non-overlap rule

This task must stay entirely out of parse-builder's current lane.

### parse-B.E. owns for this task
- `python/server.py`
- new helper module(s) under `python/app/http/`
- new direct Python tests for the extracted job observability helper behavior
- minimal updates to existing Python tests if needed

### Read-only for this task
- `src/**`
- `docs/plans/parseui-current-state-plan.md`
- `src/ParseUI.tsx`
- `src/components/parse/**`
- `src/components/annotate/**`
- `src/components/compare/**`
- `src/stores/**`
- `src/api/**`

If a frontend contract issue is discovered, document it instead of editing frontend files in this slice.

## Proposed extraction target

Preferred shape:

```text
python/app/http/
├── request_helpers.py
├── response_helpers.py
├── external_api_handlers.py
└── job_observability_handlers.py   # new
```

Adaptive split is allowed if cleaner, for example:

```text
python/app/http/
├── job_observability_handlers.py
└── worker_status_handlers.py
```

The important boundary is behavioral: move generic jobs/worker-status HTTP handling out of `python/server.py` while leaving thin wrappers there.

## Recommended scope boundary

### In scope
- `GET /api/jobs`
- `GET /api/jobs/active`
- `GET /api/jobs/{jobId}`
- `GET /api/jobs/{jobId}/logs`
- `GET /api/jobs/{jobId}/error-log` if that extraction stays clean with the same seam
- `GET /api/worker/status`
- query parsing / limit-offset coercion for the jobs routes

### Out of scope
- `_create_job`, `_set_job_progress`, `_set_job_complete`, lock internals, callback dispatch internals
- frontend/job polling hooks
- POST status endpoints (`/api/stt/status`, `/api/chat/run/status`, `/api/compute/*/status`) unless a tiny helper reuse falls out naturally without changing semantics
- OpenAPI / MCP bridge work
- auth/chat/onboarding route extraction

## TDD execution order

### 1. Start from fresh `origin/main`
Recommended bootstrap:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --prune
git switch -c refactor/job-observability-http-slice origin/main
```

### 2. Reconfirm baseline
If needed in a fresh worktree:

```bash
ln -s /home/lucas/gh/ardeleanlucas/parse/node_modules node_modules
pytest python/test_server_job_observability.py -q
npm run test -- --run
./node_modules/.bin/tsc --noEmit
rm node_modules
```

### 3. Add failing direct tests first
Before extraction, add focused direct tests for the new helper module.

Suggested new test file:
- `python/test_app_http_job_observability_handlers.py`

Suggested direct behaviors to cover:
- jobs-list query parsing (`status/statuses`, `type/types`, `speaker`, `limit`) reuses/parallels the extracted request-helper style
- invalid or missing `jobId` preserves the same error semantics
- job logs offset/limit coercion preserves defaults/fallback behavior
- jobs-active response returns the active snapshot payload only
- worker-status returns:
  - `200` + `alive: null` when mode is not persistent
  - `503` + clear message when persistent mode has no handle
  - `200` + payload when the worker is alive
  - `503` + payload when the worker has exited
- if `error-log` is included in the extraction, preserve its payload shape and not-found behavior

### 4. Extract the smallest safe slice
Implement the extraction with thin wrappers left in `python/server.py`.

Target outcome:
- `python/server.py` still exposes the same handler methods
- wrappers delegate to the new helper module(s)
- jobs/worker HTTP behavior remains unchanged
- existing tests in `python/test_server_job_observability.py` continue to pass, or need only minimal path-preserving updates

### 5. Validation
Minimum targeted checks after extraction:

```bash
pytest python/test_app_http_job_observability_handlers.py -q
pytest python/test_server_job_observability.py -q
pytest python/test_external_api_surface.py -q
python3 -m py_compile python/server.py python/app/http/job_observability_handlers.py
```

If you split into two helper modules, compile both.

### 6. Full rebuild gates
Required before calling the slice complete:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

## Files likely to change

### Expected edits
- `python/server.py`
- `python/app/http/job_observability_handlers.py` *(new, likely)*
- `python/app/http/__init__.py` *(possible)*
- `python/test_app_http_job_observability_handlers.py` *(new, likely)*
- `python/test_server_job_observability.py` *(possible, minimal only)*

### Files that should not change in this task
- `src/**`
- `python/external_api/*`
- `python/ai/*`
- `python/adapters/*`
- `docs/**`

## Branch / PR guidance

Recommended branch:

```text
refactor/job-observability-http-slice
```

Recommended PR themes:
- next backend modularization slice after merged PR #8
- extract generic jobs/worker-status handlers into app/http helper seam
- preserve route behavior and observability payloads
- explicitly isolated from parse-builder's frontend lane

## Final note

This task is intentionally the first parse-B.E. lane because it is backend-safe, already test-backed, and follows the modularization pattern now established in PRs #4 and #8. The standard is not “move code around”; it is “extract a coherent seam, preserve behavior, prove it with tests, and leave `python/server.py` thinner than before.”
