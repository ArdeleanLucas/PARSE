# parse-back-end next prompt — preserve UI-facing contracts while extracting config/import handlers

## Goal

Extract the config/import HTTP cluster from `python/server.py` into a dedicated backend handler module **without changing any UI-facing API behavior**.

## Hard boundary

- **Do not touch UI design.**
- Builder owns the original-UI parity audit.
- Your job is to keep backend behavior stable enough that the React UI can remain identical to the original workstation.

## Current context

- Current rebuild `origin/main`: `0d78bb8` (`test(compare): harden compute semantics regressions (#28)`)
- Builder is auditing current React work for UI drift versus the original PARSE UI.
- The safest parallel backend lane is contract-preserving extraction only.

## Specific task

Create a backend-only implementation PR from current `origin/main` that extracts this cluster from `python/server.py` into `python/app/http`:
- `GET /api/config`
- `PUT /api/config`
- `POST /api/concepts/import`
- `POST /api/tags/import`

Recommended new module:
- `python/app/http/project_config_handlers.py`

## Non-negotiable behavior rules

### `/api/config`
- Keep the `{ "config": ... }` wrapper.
- Preserve deep-merge semantics for `PUT /api/config`.
- Preserve the current response fields exactly.

### `/api/concepts/import`
- Preserve multipart rules, decoding, replace-mode behavior, matching rules, auto-add behavior, and response field names.

### `/api/tags/import`
- Preserve multipart rules, filename-stem tag naming, additive merge behavior, matching rules, and response field names.

## Required task steps

1. Verify current route behavior before extraction.
2. Extract the handlers into `python/app/http`.
3. Add/keep direct Python tests for the extracted handlers.
4. Keep thin server-wrapper regressions.
5. If you find a contract issue that would force frontend/UI change, report it instead of adapting the UI.

## In scope

- `python/server.py`
- `python/app/http/*`
- Python tests for the extracted routes

## Out of scope

- `src/ParseUI.tsx`
- compare/annotate React components
- UI redesign or frontend adaptation
- compute route work

## Validation requirements

Run and report at least:
- `pytest python/test_server_workspace_config.py -q`
- `pytest python/test_server_concepts_import.py -q`
- `pytest python/test_server_tags_import.py -q`
- direct tests for the new handler module
- `python3 -m py_compile python/server.py python/app/http/*.py`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Reporting requirements

In your implementation PR, include:
- exact routes extracted
- confirmation that request/response behavior was preserved
- whether any UI-facing contract risk was discovered
- exact tests run
