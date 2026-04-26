# parse-back-end next task — config/import HTTP handler slice

## Goal

Extract the remaining project-config and CSV-import HTTP routes from `python/server.py` into a dedicated application-layer handler module, keeping route behavior unchanged while reducing backend monolith pressure on current `origin/main`.

## Why this is the right next task now

- Live rebuild state is currently healthy on `origin/main` and Builder handoff PR #22 has already merged there as `10de7f4`.
- Builder is now queued onto the **compare compute-mode semantics / payload audit** preserved by merged PR #22 (`https://github.com/TarahAssistant/PARSE-rebuild/pull/22`), which explicitly centers `src/ParseUI.tsx`, `src/api/client.ts`, and possibly compute-related `python/server.py` surfaces.
- A backend-safe next slice should therefore avoid compute routes entirely.
- On current `origin/main`, PARSE already has an established backend extraction pattern:
  - `python/app/http/job_observability_handlers.py`
  - `python/app/http/auth_handlers.py`
  - `python/app/http/external_api_handlers.py`
  - shared request/response helpers under `python/app/http/request_helpers.py` and `response_helpers.py`
- But the **project config + CSV import cluster** is still inline in `python/server.py`:
  - `_api_get_config()` at ~`7691`
  - `_api_update_config()` at ~`8253`
  - `_api_post_concepts_import()` at ~`8260`
  - `_api_post_tags_import()` at ~`8403`
- Existing coverage here is still mostly server-level (`python/test_server_workspace_config.py`, `python/test_server_concepts_import.py`, `python/test_server_tags_import.py`) with **no direct app-layer handler tests** yet.

## Current grounded context

### Repo / PR topology
- Repo: `TarahAssistant/PARSE-rebuild`
- Real base: `origin/main` at `10de7f4` (`docs: add parse-builder compute-mode audit handoff (#22)`)
- Current open PRs:
  - PR #23 — this parse-back-end handoff once pushed/opened
- Recently merged context:
  - PR #22 — Builder handoff preserved on main: `https://github.com/TarahAssistant/PARSE-rebuild/pull/22`
- Root checkout warning:
  - `/home/lucas/gh/tarahassistant/PARSE-rebuild` is still on stale local branch `feat/parseui-shell-stage0-rebuild`
  - do **not** use the root checkout as merge truth; branch from fresh `origin/main`

### Existing extraction pattern to follow
Backend refactor PRs already proved the safe pattern:
- PR #12 — `refactor: extract job observability HTTP handlers`
- PR #13 — `refactor: extract auth HTTP handlers`

That pattern is:
1. new `python/app/http/*.py` helper module
2. `server.py` wrappers stay thin and behavior-preserving
3. add direct helper tests
4. retain/add thin server-wrapper regression tests
5. no client-contract drift

## Specific task

Create the next backend slice around the **project config/import surface**.

### In scope
Extract a coherent cluster such as:
- `GET /api/config`
- `PUT /api/config`
- `POST /api/concepts/import`
- `POST /api/tags/import`

Recommended module shape:
- `python/app/http/project_config_handlers.py`

Recommended responsibilities:
- build config response payloads without changing the `{ "config": ... }` wrapper
- preserve deep-merge semantics for `PUT /api/config`
- preserve multipart validation / CSV matching behavior for both import endpoints
- preserve current error semantics and response field names exactly

## Important non-overlap boundary

This slice must stay **outside** Builder PR #22’s compute-mode audit.

### Do not touch
- compare compute semantics
- `/api/compute/*`
- `src/ParseUI.tsx`
- `src/api/client.ts`
- CLEF/contact-lexeme compute routing unless required for an unrelated import helper bug (unlikely)

### Allowed backend surfaces
- `python/server.py`
- `python/app/http/*`
- Python tests for the config/import routes

## Existing behavior that must remain unchanged

### `/api/config`
- `GET /api/config` must still return `{ "config": ... }`
- payload must still be built from `_workspace_frontend_config(load_ai_config(_config_path()))`
- `PUT /api/config` must still deep-merge onto the existing AI config before writing
- response must remain `{ "success": True, "config": merged }`

### `/api/concepts/import`
Keep all current semantics unless a test proves a bug:
- multipart/form-data requirement
- UTF-8 decoding behavior
- `mode=replace` support
- match by `id`, then case-insensitive `concept_en`
- auto-add new concepts when the uploaded row doesn’t match an existing one
- preserve response fields: `ok`, `matched`, `added`, `total`, `mode`

### `/api/tags/import`
Keep all current semantics unless a test proves a bug:
- multipart/form-data requirement
- tag-name default from filename stem
- additive merge into `parse-tags.json`
- match by `id` or `concept_en`
- preserve response fields: `ok`, `tagId`, `tagName`, `color`, `matchedCount`, `missedCount`, `missedLabels`, `totalTagsInFile`

## Likely files to touch

Primary expected files:
- `python/app/http/project_config_handlers.py` (new)
- `python/app/http/__init__.py`
- `python/server.py`
- `python/test_app_http_project_config_handlers.py` (new)

Expected regression surfaces to update or preserve:
- `python/test_server_workspace_config.py`
- `python/test_server_concepts_import.py`
- `python/test_server_tags_import.py`

Potentially useful shared helpers already present:
- `python/app/http/request_helpers.py`
- `python/app/http/response_helpers.py`

## Validation requirements

Run and report at least:
- `pytest python/test_app_http_project_config_handlers.py -q`
- `pytest python/test_server_workspace_config.py -q`
- `pytest python/test_server_concepts_import.py -q`
- `pytest python/test_server_tags_import.py -q`
- `pytest python/test_external_api_surface.py -q` if route dispatch or contract-table behavior is touched
- `python3 -m py_compile python/server.py python/app/http/project_config_handlers.py python/app/http/__init__.py`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

### Rebuild-worktree note
If this worktree lacks frontend dependencies, use the known rebuild-lane workaround:
- temporarily symlink `node_modules` from `/home/lucas/gh/ardeleanlucas/parse/node_modules`
- remove the symlink after validation

## Reporting requirements

Open a fresh implementation PR from current `origin/main`.

In the PR body, include:
- exact routes extracted
- confirmation that response shapes and error behavior were preserved
- exact Python tests added/updated
- whether any behavior drift was discovered and how it was contained

## Academic / fieldwork considerations

- Project metadata and concept import are not cosmetic; they shape the concept inventory that later drives comparative analysis and export.
- Silent response-shape drift here can make the workstation look “empty” or cause import-side metadata loss that propagates into comparative work.
- This slice should therefore optimize for **contract stability and reproducibility**, not clever rewrites.

## Out of scope

- compare compute semantics / payload changes (Builder owns that via PR #22)
- auth routes (already extracted in PR #13)
- job observability routes (already extracted in PR #12)
- external API / OpenAPI / MCP bridge changes unless you discover an incidental import dependency that must be split mechanically

## What comes after this task

If this slice lands cleanly, the next parse-back-end candidate can continue the same refactor pattern on another isolated inline HTTP cluster — but only after re-checking live overlap against whatever Builder is actively touching at that time.
