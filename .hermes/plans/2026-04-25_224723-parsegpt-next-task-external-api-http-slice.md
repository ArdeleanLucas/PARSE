# ParseGPT next task — external API HTTP handler extraction slice

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Date:** 2026-04-25
**Owner:** ParseGPT
**Status:** queued / ready after PR #4 exists as the backend helper baseline

## Goal

Continue the PARSE rebuild in a backend-only lane that stays clear of parse-builder's ParseUI shell work by extracting the next coherent `python/server.py` seam: the built-in docs + HTTP MCP bridge handler logic.

## Why this is the right next task

- `parse-builder` now has an explicit frontend shell handoff in rebuild PR #5 and is expected to occupy the `ParseUI` Stage-1 lane.
- ParseGPT already established the backend modularization pattern in rebuild PR #4 by extracting request/response HTTP helpers under `python/app/http/`.
- `python/server.py` is still very large (**8896 lines** verified in the rebuild repo).
- The external API HTTP surface is a compact, behavior-critical seam with existing integration coverage, making it a good candidate for the next safe extraction.

## Current grounded context

Verified in the rebuild repo before writing this prompt:
- Open rebuild PRs:
  - PR #3 — `feat/parseui-shell-stage0-rebuild` → Stage-0 ParseUI shell regression coverage
  - PR #4 — `refactor/backend-http-slice` → request/response helper extraction
  - PR #5 — `docs/parse-builder-stage1-handoff` → parse-builder prompt for Stage 1 shell work
- `python/server.py` → **8896 lines**
- Existing extracted backend helpers already live under `python/app/http/`:
  - `static_paths.py`
  - `request_helpers.py`
  - `response_helpers.py`
- Relevant remaining seam locations in `python/server.py`:
  - `_execute_mcp_http_tool()` around lines **2346-2382**
  - `_handle_builtin_docs_get()` around lines **6059-6070**
  - `_api_get_mcp_exposure()` around lines **7006-7012**
  - `_api_get_mcp_tools()` around lines **7014-7020**
  - `_api_get_mcp_tool()` around lines **7022-7036**
  - `_api_post_mcp_tool()` around lines **7038-7044**
- Existing external API integration coverage already exists in:
  - `python/test_external_api_surface.py`
  - that file currently covers `/openapi.json`, `/docs`, `/redoc`, `/api/mcp/tools`, MCP mode validation, and MCP tool execution via live HTTP.

## Non-overlap rule

This task must stay entirely out of parse-builder's frontend shell lane.

### ParseGPT owns for this task
- `python/server.py`
- new modules under `python/app/http/`
- new backend Python tests for extracted external API HTTP helpers
- targeted updates to existing Python external API tests if required by the extraction

### Read-only for this task
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/parse/**`
- `src/components/annotate/**`
- `src/components/compare/**`
- `src/components/compute/**`
- `src/components/shared/**`
- `src/hooks/**`
- `src/stores/**`
- `src/api/client.ts`
- `src/api/types.ts`

If the extraction reveals a frontend contract issue, document it instead of editing shared/frontend surfaces in this task.

## Proposed extraction target

Extract a new helper module under `python/app/http/` for the external API HTTP surface served by `python/server.py`.

### Preferred target direction

```text
python/app/http/
├── __init__.py
├── static_paths.py
├── request_helpers.py
├── response_helpers.py
└── external_api_handlers.py    # new
```

Adaptive split is allowed if cleaner, for example:

```text
python/app/http/
├── docs_handlers.py            # optional
└── mcp_bridge_handlers.py      # optional
```

The important boundary is behavioral: move built-in docs + HTTP MCP bridge logic out of `python/server.py` while leaving thin wrapper methods there.

## Recommended scope boundary

### In scope
- built-in docs endpoint mapping for:
  - `/openapi.json`
  - `/docs`
  - `/redoc`
- MCP bridge mode handling and catalog/tool lookup behavior for:
  - `GET /api/mcp/exposure`
  - `GET /api/mcp/tools`
  - `GET /api/mcp/tools/{toolName}`
  - `POST /api/mcp/tools/{toolName}`
- extraction of `_execute_mcp_http_tool()` if that produces a cleaner helper seam

### Out of scope
- general API route-dispatch extraction
- frontend/client changes
- catalog-generation redesign inside `python/external_api/catalog.py`
- OpenAPI schema redesign inside `python/external_api/openapi.py`
- chat/session route extraction

## Step-by-step task plan

### 1. Freeze branch baseline on the backend lane
Because this slice touches the same backend file family as PR #4, stack it on the backend helper branch rather than on the frontend shell branch.

Preferred bootstrap:
```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --prune
git switch -c refactor/external-api-http-slice origin/refactor/backend-http-slice
```

That makes the branch explicitly depend on PR #4 and avoids rebasing the same `python/server.py` seam later.

### 2. Reconfirm validation baseline
If needed, create the temporary node_modules symlink for frontend gates:
```bash
ln -s /home/lucas/gh/ardeleanlucas/parse/node_modules node_modules
```

Then run:
```bash
pytest python/test_external_api_surface.py -q
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

Also run targeted Python checks once the new helper test file exists.

### 3. Read the current seam and dependency shape
Inspect exactly how the current handler methods depend on:
- request path/query parsing
- request base URL
- `build_openapi_document()` / `render_swagger_ui_html()` / `render_redoc_html()`
- `resolve_catalog_mode()`
- `build_mcp_http_catalog()`
- `get_mcp_tool_entry()`
- `_get_chat_runtime()`
- `_build_workflow_runtime()`
- `_execute_mcp_http_tool()`

Document what can be made pure and what needs an injected runtime/provider callable.

### 4. Write failing tests first
Before extraction, add focused unit-style tests for the extracted helper behavior.

Suggested new test file:
- `python/test_app_http_external_api_handlers.py`

Suggested behaviors to cover:
- built-in docs route mapping returns the correct payload/content-type intent for:
  - `/openapi.json`
  - `/docs`
  - `/redoc`
- non-doc paths return no match / falsey result
- invalid MCP `mode` preserves the same error semantics
- exposure endpoint returns only the `catalog["exposure"]` payload
- tools endpoint returns the full catalog payload
- single-tool lookup preserves not-found semantics
- POST tool execution rejects non-object args with the same error message
- adapter special case for `mcp_get_exposure_mode` still returns `mcp_exposure_payload(...)`

If purity requires a small response-spec abstraction, keep it tiny and explicit.

### 5. Extract the smallest safe slice
Implement the extraction with thin wrappers left in `python/server.py`.

Target outcome:
- `python/server.py` still exposes the same handler methods
- wrappers delegate to the new app/http helper module(s)
- external HTTP behavior remains unchanged
- existing integration tests in `python/test_external_api_surface.py` still pass unchanged, or only need minimal path-preserving updates

### 6. Run targeted validation
Minimum targeted checks after extraction:
```bash
pytest python/test_app_http_external_api_handlers.py -q
pytest python/test_external_api_surface.py -q
python -m py_compile python/server.py python/app/http/external_api_handlers.py
```

If the final split uses two helper modules, compile both.

### 7. Run full rebuild-repo gates
Required before calling the slice complete:
```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

### 8. Package as a stacked rebuild-repo PR
If the task completes cleanly, push and open a **stacked PR** in:
- `TarahAssistant/PARSE-rebuild`

PR base should be:
- `refactor/backend-http-slice`

PR body should explicitly say:
- this is a backend modularization slice stacked on PR #4
- it is intentionally isolated from parse-builder's shell lane and PR #3 / PR #5

## Files likely to change

### Expected edits
- `python/server.py`
- `python/app/http/__init__.py`
- `python/app/http/external_api_handlers.py` *(new, likely)*
- `python/test_app_http_external_api_handlers.py` *(new, likely)*
- `python/test_external_api_surface.py` *(possible, only if minimal adjustment is required)*

### Files that should not change in this task
- any `src/components/parse/**` files
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/api/client.ts`
- `src/api/types.ts`

## Validation / success criteria

This task is done only when all are true:
- the built-in docs + HTTP MCP bridge seam is extracted from `python/server.py` into `python/app/http/`
- `python/server.py` keeps thin wrapper methods with preserved behavior
- new direct tests prove the extracted helper behavior
- existing external API integration tests are green
- full Vitest suite is green
- TypeScript is green
- Python compile is green
- changes are packaged as a stacked rebuild-repo PR

## Risks / pitfalls

- `mode` parsing is duplicated across multiple MCP GET/POST handlers; extraction should reduce duplication without changing error text.
- `_execute_mcp_http_tool()` has a subtle adapter special case for `mcp_get_exposure_mode`; tests must lock this down before moving it.
- docs handlers depend on both JSON and text response paths; do not over-abstract the response shape too early.
- Do not drift into general route-dispatch extraction in the same slice.
- Do not touch frontend files in the same task; keep collision risk with parse-builder near zero.

## Open questions to answer at execution time

1. Should docs handlers and MCP bridge handlers live in one module or two?
2. Should `_execute_mcp_http_tool()` move with the MCP bridge handlers, or remain in `python/server.py` for this slice?
3. Is a small response-spec dataclass/typed dict warranted for docs handlers, or are simple pure helper functions enough?

## Recommended branch name

```text
refactor/external-api-http-slice
```

## Final note

This task is intentionally scoped as the next backend analogue of the earlier extractions: small, behavior-preserving, test-backed, stacked cleanly on PR #4, and safe to run in parallel with parse-builder's Stage-1 frontend shell work.
