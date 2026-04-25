# ParseGPT next task — backend HTTP helper extraction slice

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Date:** 2026-04-25
**Owner:** ParseGPT
**Status:** queued / ready to execute after parse-builder is running in the rebuild repo

## Goal

Continue the PARSE rebuild in a lane that does **not** collide with parse-builder's frontend `ParseUI` shell work by extracting the next safe backend slice from `python/server.py`: HTTP request/response helper logic.

## Why this is the right next task

- `parse-builder` is expected to occupy the frontend shell lane around `src/ParseUI.tsx`.
- The rebuild repo already has one proven backend extraction pattern:
  - `python/app/http/static_paths.py`
  - `python/app/services/workspace_config.py`
- `python/server.py` is still extremely large (**8896 lines** last verified in rebuild repo).
- The handler-level HTTP helper methods are a coherent next seam and can be extracted with thin wrapper methods while preserving behavior.

## Current grounded context

Verified in rebuild repo before writing this task:
- `src/ParseUI.tsx` → **5328 lines**
- `src/ParseUI.test.tsx` → **1007 lines**
- `python/server.py` → **8896 lines**
- `python/ai/chat_tools.py` → **6408 lines**
- Existing extracted backend helpers already live under:
  - `python/app/http/static_paths.py`
  - `python/app/services/workspace_config.py`
- Relevant remaining HTTP helper cluster in `python/server.py` is around:
  - `_request_path()`
  - `_request_query_params()`
  - `_path_parts()`
  - `_read_json_body()`
  - `_send_json()`
  - `_send_json_error()`

## Non-overlap rule

This task must avoid stepping on parse-builder's likely shell lane.

### ParseGPT owns for this task
- `python/server.py`
- new modules under `python/app/http/`
- new backend Python tests for extracted HTTP helpers

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

If backend extraction reveals a client/server contract issue, document it rather than silently editing frontend/shared surfaces in this task.

## Proposed extraction target

Extract a new backend helper module (or pair of modules) under `python/app/http/` for request parsing + JSON response behavior.

### Preferred target direction

```text
python/app/http/
├── __init__.py
├── static_paths.py            # already exists
├── request_helpers.py         # new
└── response_helpers.py        # new, if needed
```

The exact split is adaptive, not canonical. One combined helper module is acceptable if that is the cleaner boundary.

## Step-by-step task plan

### 1. Freeze branch baseline
Create a fresh branch from the rebuild repo context branch, not the live/oracle repo.

Preferred bootstrap:
```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --prune
git switch -c refactor/backend-http-slice origin/docs/rebuild-repo-context
```

If this task should include the stage-0 ParseUI shell regression commit for consistency with the current rebuild lane, cherry-pick it explicitly and note it in the branch log. Otherwise leave that frontend-only commit out.

### 2. Reconfirm validation baseline
If needed, create the temporary node_modules symlink:
```bash
ln -s /home/lucas/gh/ardeleanlucas/parse/node_modules node_modules
```

Then run:
```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

Also run targeted Python checks once the backend test files exist.

### 3. Read the current HTTP helper seam in `python/server.py`
Read the class region around the handler methods and map exact dependencies for:
- request path/query parsing
- JSON request body decoding
- JSON response encoding and headers
- error JSON response behavior

Document whether each helper can be made pure or needs a thin adapter over `BaseHTTPRequestHandler` state.

### 4. Write failing tests first
Before extraction, add focused tests for the target helper behavior.

Suggested new tests:
- `python/test_app_http_request_helpers.py`
- `python/test_app_http_response_helpers.py` (or one combined file)

Suggested behaviors to cover:
- request path parsing preserves `/` fallback
- query parameter parsing keeps blank values where expected
- path parts are URL-decoded correctly
- JSON body decoding rejects invalid JSON with the same error semantics
- empty body handling matches current required/optional behavior
- JSON responses preserve UTF-8 encoding and expected content-type / length behavior
- JSON error responses still wrap as `{ "error": ... }`

If a helper cannot be tested purely, create the smallest harness possible and keep the extracted logic itself pure.

### 5. Extract the smallest safe slice
Implement extraction with thin wrappers in `python/server.py`.

Target outcome:
- `python/server.py` still exposes the same handler methods
- each wrapper delegates to the new app/http helper(s)
- external behavior remains unchanged

### 6. Run targeted validation
Minimum targeted checks after extraction:
```bash
pytest python/test_app_http_request_helpers.py -q
pytest python/test_app_http_response_helpers.py -q
python -m py_compile python/server.py python/app/http/request_helpers.py python/app/http/response_helpers.py
```

Adjust filenames if the final extraction uses one combined module/test file.

### 7. Run full rebuild-repo gates
Required before calling the slice complete:
```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

### 8. Package as a rebuild-repo PR
If the task completes cleanly, push and open a PR in:
- `TarahAssistant/PARSE-rebuild`

The PR body should explicitly say this is a backend modularization slice in the rebuild lane, not a live/oracle PARSE change.

## Files likely to change

### Expected edits
- `python/server.py`
- `python/app/http/__init__.py`
- `python/app/http/request_helpers.py` *(new, likely)*
- `python/app/http/response_helpers.py` *(new, likely)*
- `python/test_app_http_request_helpers.py` *(new, likely)*
- `python/test_app_http_response_helpers.py` *(new, likely)*

### Files that should not change in this task
- any `src/components/parse/**` files
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/api/client.ts`
- `src/api/types.ts`

## Validation / success criteria

This task is done only when all are true:
- the target HTTP helper seam is extracted into `python/app/http/`
- `python/server.py` behavior is preserved through thin wrappers
- new tests prove the extracted behavior directly
- full Vitest suite is green
- TypeScript is green
- Python compile is green
- changes are packaged as a rebuild-repo PR

## Risks / pitfalls

- `_read_json_body()` may have subtle behavior around required vs optional bodies and error messages; tests must lock this down before extraction.
- Response helpers may implicitly depend on handler state/order of `send_response`, `send_header`, and `end_headers`; avoid over-abstracting too early.
- Do not drift into route extraction in this slice — keep it to helper extraction only.
- Do not touch frontend files in the same task; keep collision risk with parse-builder near zero.

## Open questions to answer at execution time

1. Should request parsing + response encoding live in one helper module or two?
2. Is there enough pure logic to avoid mock-heavy handler tests?
3. Does the current rebuild branch for execution need the stage-0 ParseUI shell regression commit, or is `origin/docs/rebuild-repo-context` alone the better base for this backend-only slice?

## Recommended branch name

```text
refactor/backend-http-slice
```

## Final note

This task is intentionally scoped to be the backend analogue of the earlier `static_paths` / `workspace_config` extraction: small, behavior-preserving, test-backed, and safe to run in parallel with parse-builder's shell lane.
