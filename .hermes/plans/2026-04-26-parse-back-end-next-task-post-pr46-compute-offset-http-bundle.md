# parse-back-end next task — post-PR46 compute + offset HTTP contract bundle

## Goal

Ship **one fresh backend-only parse-back-end implementation PR** from the latest `origin/main` _after finishing PR #46_ that extracts and regression-hardens the **generic compute + timestamp-offset HTTP surface** without changing any UI-facing behavior.

This is a contract-preservation task, not a product redesign task.

## Why this is the right next task now

- **PR #46** has already landed on `origin/main` as the ORTH runtime/docs/script reconciliation slice.
- **PR #45** has also landed as the queued Builder compute-contract handoff.
- **PR #42** remains a separate local-maintenance/worktree-hygiene lane.
- **PRs #41 / #43 / #36** remain frontend/annotate/Builder lanes.

So the next real parse-back-end slice should be:
- backend-only
- post-PR46
- adjacent to Builder’s compute-contract audit, but not overlapping its frontend work
- explicitly zero-drift on route semantics

The strongest grounded next gap is the **server-side compute + offset HTTP contract** still living inline in `python/server.py`.

## Current grounded evidence

### 1. The active frontend now depends on these routes heavily
The React shell currently uses:
- `startCompute()` / `pollCompute()` for compare compute jobs
- `detectTimestampOffset()` / `pollOffsetDetectJob()` / `applyTimestampOffset()` for annotate timestamp correction

Those flows are now surfaced directly in:
- `src/ParseUI.tsx`
- `src/hooks/useComputeJob.ts`
- `src/api/client.ts`

### 2. The backend route contract is still inline and concentrated in one large monolith region
In `python/server.py` today:
- `_api_post_offset_detect()` starts at ~`6589`
- `_api_post_offset_detect_from_pair()` starts at ~`6621`
- `_api_post_offset_apply()` starts at ~`6657`
- `_api_post_compute_start()` starts at ~`7129`
- `_api_post_compute_status()` starts at ~`7165`
- route dispatch glue lives around ~`6318-6331`

This is exactly the kind of backend slice that has previously been worth extracting into app-layer HTTP helpers.

### 3. The surface has compatibility semantics that are important but currently under-documented in tests
Current server/OpenAPI behavior includes all of these:
- `POST /api/compute/status`
- `POST /api/compute/{computeType}`
- `POST /api/compute/{computeType}/status`
- compatibility alias: `POST /api/{computeType}/status`
- `POST /api/offset/detect`
- `POST /api/offset/detect-from-pair`
- `POST /api/offset/apply`

The compatibility alias is explicitly present in `python/external_api/openapi.py` and in `server.py` dispatch logic.

### 4. There is strong algorithm/client coverage, but not a dedicated server-HTTP regression bundle for these routes
Observed current coverage:
- backend algorithm tests for offset logic exist:
  - `python/test_offset_detect_monotonic.py`
  - `python/test_offset_manual_pairs.py`
  - `python/test_offset_apply_protected.py`
  - `python/test_offset_job_failure_paths.py`
- client polling tests exist:
  - `src/__tests__/pollOffsetDetectJob.test.ts`

But there is **no dedicated** `python/test_server_compute*.py` or `python/test_server_offset*.py` route-level bundle on current `main`.

That makes the live HTTP contract a good backend-owned next slice.

## Source of truth

Primary backend sources:
- `python/server.py`
- `python/external_api/openapi.py`
- `python/workers/compute_worker.py`
- `python/test_external_api_surface.py`
- `src/api/client.ts` (read-only contract consumer)
- `src/ParseUI.tsx` (read-only contract consumer)
- `src/hooks/useComputeJob.ts` (read-only contract consumer)
- `AGENTS.md`

## Specific task

Create **one fresh parse-back-end implementation PR** from the latest `origin/main` that extracts and hardens the compute + offset HTTP contract.

### Required implementation direction

1. **Extract the generic compute HTTP handlers from `python/server.py`.**
   Create an app-layer helper module (for example `python/app/http/compute_handlers.py`) for:
   - compute start
   - generic compute status
   - typed compute status
   - compatibility alias semantics, if you keep alias handling centralized

2. **Extract the offset HTTP handlers from `python/server.py`.**
   Create an app-layer helper module (for example `python/app/http/offset_handlers.py`) for:
   - offset detect
   - offset detect from pair(s)
   - offset apply

3. **Preserve all live compatibility rules.**
   Explicitly keep current contract behavior unless a bug is proven:
   - `jobId` and `job_id` both accepted for polling
   - typed status rejects mismatched compute job types
   - compatibility alias `POST /api/{computeType}/status` continues to work
   - compute start still records `compute:<type>` job type
   - offset detect still accepts snake_case + camelCase option variants
   - offset detect-from-pair still accepts both single-pair and `pairs[]` body shapes
   - offset apply still accepts `offsetSec` and `offset_sec`
   - zero / non-finite offset apply input remains rejected with the current semantics

4. **Add dedicated route-level backend tests.**
   Add direct helper tests and thin server-wrapper regressions that prove:
   - compute start validation and job creation behavior
   - generic vs typed compute status behavior
   - compatibility alias behavior
   - callback URL / metadata passthrough if still part of the route contract
   - offset detect request-shape compatibility
   - offset apply validation + protected-lexeme-safe semantics remain intact at the HTTP layer

5. **Keep OpenAPI honest.**
   If the extraction exposes any drift between implementation and spec, patch `python/external_api/openapi.py` and its tests in the same PR.
   Do not widen the public API without need.

## In scope

- `python/server.py`
- new `python/app/http/compute_handlers.py`
- new `python/app/http/offset_handlers.py`
- direct tests for those helpers
- thin server regression tests for compute/offset HTTP routes
- narrowly required OpenAPI/test updates

## Out of scope

- PR #46 ORTH contract implementation
- PR #45 Builder compute-contract frontend work
- PR #42 worktree-hygiene maintenance
- frontend TypeScript / React changes
- changes to actual offset-detection algorithms unless a real bug is found during extraction
- UI copy or workflow redesign

## Validation requirements

Run and report at least:
- targeted backend tests for the new compute/offset HTTP bundle
- `python3 -m py_compile` for touched Python files
- `PYTHONPATH=python python3 -m pytest -q`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Reporting requirements

Open **one fresh parse-back-end implementation PR** from the latest `origin/main`.

In the PR body include:
- which route behaviors were preserved explicitly
- any implementation/spec drift found and corrected
- exact handler modules introduced
- confirmation of non-overlap with PRs `#46`, `#45`, `#42`, `#41`, `#43`, and `#36`
- exact tests run

## Academic / fieldwork considerations

- Compute and offset routes sit directly on top of reproducibility-critical linguistic operations: cognate clustering, contact-lexeme population, and timestamp realignment.
- Silent route drift here is especially dangerous because both the UI and future agent tooling may appear to work while dispatching slightly different compute types or validation rules.
- Extracting and regression-locking this HTTP bundle improves auditability without changing scholarly behavior.