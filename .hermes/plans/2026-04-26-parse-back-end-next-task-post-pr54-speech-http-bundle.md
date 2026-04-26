# parse-back-end next task — post-PR54 speech HTTP bundle

## Goal

Ship **one fresh backend-only parse-back-end implementation PR** from the latest `origin/main` _after the active PR #54 lexeme/media-search extraction lane_ that extracts the remaining **speech/annotation-assist HTTP cluster** from `python/server.py` into app-layer HTTP helpers, with direct tests and zero UI-facing contract drift.

This bundle should cover the still-inline routes that serve Annotate-mode audio preparation and concept-assist workflows:

- `GET /api/stt-segments/{speaker}`
- `POST /api/normalize`
- `POST /api/normalize/status`
- `POST /api/stt`
- `POST /api/stt/status`
- `POST /api/suggest`

## Why this is the right next task now

- **PR #54** is the active parse-back-end implementation lane and already owns the lexeme-note + spectrogram + lexeme-search extraction bundle.
- The earlier backend successor handoff **PR #51** is closed because its task was consumed by PR #54; there is **no live backend successor PR** now.
- `.hermes/automation/state/parse-back-end.json` still says parse-back-end is waiting for a new backend/external-api/server-safe handoff.
- The next coherent backend-owned cleanup on current `origin/main` is the adjacent **speech-job / suggestion HTTP cluster**: still inline, still contract-sensitive, and still lacking dedicated app-layer extraction coverage.

This keeps parse-back-end on a narrow backend seam while Builder continues frontend-only work.

## Current grounded context

### Active/open PR topology at handoff time
- **PR #54** — `refactor: extract lexeme and media search HTTP handlers` (active parse-back-end implementation lane; checks green)
- **PR #53** — Builder queued successor handoff
- **PR #52** / **PR #50** — Builder implementation lanes
- **PR #42** — older backend maintenance/worktree-hygiene prompt; keep separate and do not let it redefine the current implementation queue

### Current-main evidence for the next backend slice
On a fresh `origin/main` worktree (`/home/lucas/gh/worktrees/PARSE-rebuild/pr53-compare-config-cleanup`, commit `6b3ed31`), the following routes remain inline in `python/server.py`:

- `python/server.py:6363` — `_api_get_stt_segments`
- `python/server.py:6543` — `_api_post_normalize`
- `python/server.py:6683` — `_api_post_normalize_status`
- `python/server.py:6786` — `_api_post_stt_start`
- `python/server.py:6828` — `_api_post_stt_status`
- `python/server.py:6843` — `_api_post_suggest`

Frontend/client surfaces already depend on them:
- `src/api/client.ts:325-342` — `startSTT()` / `pollSTT()`
- `src/api/client.ts:578-586` — `requestSuggestions()`
- `src/api/client.ts:809-825` — `startNormalize()` / `pollNormalize()`
- `src/hooks/useSuggestions.ts:124` — concept suggestion flow

OpenAPI / route-surface coverage already names these endpoints:
- `python/external_api/openapi.py` includes `/api/stt-segments/{speaker}`, `/api/stt`, `/api/stt/status`, `/api/normalize`, `/api/normalize/status`, `/api/suggest`
- `python/test_external_api_surface.py` asserts those paths exist

### Important behavior that must be preserved
Current inline semantics are not trivial wrappers; preserve them exactly unless you find a real bug:

1. **`GET /api/stt-segments/{speaker}`**
   - normalizes speaker id
   - returns HTTP 200 with `{"speaker": ..., "segments": []}` when cache is missing
   - does **not** raise 404 for empty cache
   - preserves cached metadata (`source_wav`, `language`, etc.) when present

2. **`POST /api/normalize`**
   - accepts `speaker`
   - accepts either `sourceWav` or `source_wav`
   - derives default source WAV from `_annotation_primary_source_wav()` when omitted
   - accepts callback URL via the existing job-callback mapping helper
   - creates a `normalize` job and returns running job payload

3. **`POST /api/normalize/status`**
   - accepts either `jobId` or `job_id`
   - validates job existence and `type == "normalize"`
   - returns `_job_response_payload(job)`

4. **`POST /api/stt`**
   - requires `speaker` and `sourceWav` / `source_wav`
   - optional `language`
   - accepts callback URL via the existing mapping helper
   - creates an `stt` job and launches the compute runner
   - preserves current response casing behavior (`jobId` returned; client normalizes)

5. **`POST /api/stt/status`**
   - accepts `jobId` or `job_id`
   - validates job existence and `type == "stt"`
   - returns `_job_response_payload(job)`

6. **`POST /api/suggest`**
   - requires `speaker`
   - accepts both `conceptIds` and `concept_ids`
   - tries provider `suggest_concepts()` first
   - falls back to `_load_cached_suggestions()` on provider failure or empty provider output
   - always returns `{ "suggestions": [...] }`

## Source of truth

Use these as the implementation source of truth:
- `python/server.py`
- `src/api/client.ts`
- `python/external_api/openapi.py`
- `python/test_external_api_surface.py`
- `AGENTS.md`

Useful current-main audit worktree:
- `/home/lucas/gh/worktrees/PARSE-rebuild/pr53-compare-config-cleanup`

Active implementation PR to avoid overlapping with:
- **PR #54** `refactor: extract lexeme and media search HTTP handlers`

## Specific task

Create **one fresh parse-back-end implementation PR** from the latest `origin/main` after PR #54’s scope that extracts the speech/annotation-assist HTTP cluster into app-layer helpers.

### Required implementation direction

1. **Extract the route logic out of `python/server.py`.**
   - Introduce one or more new app-layer helper modules under `python/app/http/`
   - Good examples: `speech_http_handlers.py`, `stt_http_handlers.py`, or similar
   - Thin `RangeRequestHandler` wrapper methods in `python/server.py` should remain, but the core request/response logic should move out

2. **Preserve request aliasing and response shapes exactly.**
   - Keep `jobId` / `job_id` acceptance where it already exists
   - Keep `sourceWav` / `source_wav` alias handling
   - Keep the HTTP-200 empty STT-segment cache behavior
   - Keep suggestion fallback behavior
   - Do **not** introduce UI-visible contract drift

3. **Add direct app-layer tests plus thin wrapper regressions.**
   At minimum, add/update tests that cover:
   - missing STT cache still returns `200` with empty `segments`
   - normalize start path: speaker validation, source-wav fallback, conflict handling, callback URL pass-through
   - normalize status path: missing/unknown/wrong-type job handling
   - STT start path: speaker/source validation, optional language, callback URL pass-through
   - STT status path: missing/unknown/wrong-type job handling
   - suggest path: provider success, provider failure fallback, cached fallback, concept-id alias handling
   - route-dispatch/server-wrapper coverage for the extracted endpoints

4. **Patch OpenAPI only if you find real runtime/spec drift.**
   - If runtime behavior already matches docs, leave the docs alone
   - If you discover undocumented fields/aliases or incorrect schemas, patch `python/external_api/openapi.py` and extend `python/test_external_api_surface.py`

5. **Keep this backend-only.**
   - No frontend/UI file changes unless a tiny test fixture or contract assertion absolutely requires it
   - No behavior changes for Builder-owned flows beyond preserving backend contract correctness

## In scope

- `python/server.py`
- new helper module(s) under `python/app/http/`
- new/updated backend tests under `python/test_*`
- `python/external_api/openapi.py` only if implementation/spec drift is real
- `python/test_external_api_surface.py` only if docs change or need stronger assertions

## Out of scope

- PR #54 lexeme/media-search extraction work
- Builder PRs #50, #52, #53
- backend maintenance/worktree cleanup from PR #42
- frontend/UI redesign or client changes
- MCP or chat route extraction
- onboarding / annotation save refactors

## Validation requirements

Run and report at least:
- targeted backend tests for the new helper module(s)
- targeted server route-wrapper tests for these endpoints
- `python3 -m py_compile` on changed Python files
- `PYTHONPATH=python python3 -m pytest -q`
- `npm run test -- --run` (only to confirm no frontend regressions from contract/doc updates)
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- optional lightweight HTTP smoke if you adjust OpenAPI/runtime docs

## Reporting requirements

Open **one fresh parse-back-end implementation PR** from current `origin/main`.

In the PR body include:
- confirmation this is the post-PR54 successor slice
- which routes were extracted
- which exact request/response compatibility points were preserved
- whether OpenAPI needed changes
- exact tests run
- explicit statement of non-overlap with PR #54 and the active Builder lanes

## Academic / fieldwork considerations

- These endpoints support transcription preparation, audio normalization, and concept suggestion in real annotation workflows; silent contract drift here causes wasted fieldwork time and inconsistent operator behavior.
- The `stt-segments` empty-cache 200 behavior is especially important for a calm UX during speaker switching and partial project states.
- Suggestion fallback behavior matters for reproducibility when provider-backed assistive calls are unavailable; preserving cached fallback semantics keeps the workstation usable offline or during API outages.
