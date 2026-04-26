# parse-back-end next task — backend-only config/import extraction with zero UI drift

## Goal

Extract the config/import HTTP cluster from `python/server.py` into a dedicated backend handler module while preserving request/response behavior exactly and avoiding any contract drift that could force React UI changes.

## Hard boundary

- **Do not touch UI design.**
- The React PARSE UI must remain identical to the original workstation.
- Your responsibility is backend-only parity support: preserve shapes, semantics, and error behavior so the frontend can stay visually unchanged.

## Why this is the right task now

- Lucas explicitly locked the product direction: no React UI re-imagining.
- Current rebuild `origin/main` is `0d78bb8` (`test(compare): harden compute semantics regressions (#28)`).
- Builder is being redirected to audit and correct any UI drift against the original workstation.
- The safest parallel parse-back-end lane is therefore a backend-only extraction that preserves existing API contracts exactly.

## Specific task

Extract this cluster from `python/server.py` into a dedicated `python/app/http` helper module:
- `GET /api/config`
- `PUT /api/config`
- `POST /api/concepts/import`
- `POST /api/tags/import`

Recommended module:
- `python/app/http/project_config_handlers.py`

## Non-negotiable behavior rules

### `/api/config`
- Keep the `{ "config": ... }` response wrapper.
- Preserve deep-merge semantics for `PUT /api/config`.
- Preserve response shape: `{ "success": True, "config": merged }`.

### `/api/concepts/import`
- Preserve multipart requirements, decoding, replace-mode behavior, matching rules, auto-add behavior, and current response field names.

### `/api/tags/import`
- Preserve multipart requirements, filename-stem tag naming, additive merge behavior, matching rules, and current response field names.

## In scope

- `python/server.py`
- `python/app/http/*`
- direct Python tests for the extracted handler module
- thin server-wrapper regressions for the touched routes

## Out of scope

- `src/ParseUI.tsx`
- compare/annotate component changes
- compute route semantics
- frontend store or client redesign
- any API shape change that would require visible UI adaptation

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

Open a fresh parse-back-end implementation PR from current `origin/main`.

In the PR body, include:
- exact routes extracted
- confirmation that request/response behavior was preserved
- confirmation that no UI-facing contract drift was introduced
- exact tests run
