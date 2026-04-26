# parse-back-end next task — post-PR49 lexeme-notes + spectrogram/search HTTP bundle

## Goal

Ship **one fresh backend-only parse-back-end implementation PR** from the latest `origin/main` _after the PR #47 compute+offset HTTP slice_ that extracts and regression-hardens the remaining **lexeme notes + spectrogram + lexeme search HTTP contract** without changing any UI-facing behavior.

This is a behavior-preserving backend modularization and contract-test task.

## Why this is the right next task now

- **PR #49** is the active parse-back-end implementation follow-through for the prior compute+offset handoff.
- **PR #48** is the queued Builder successor for Actions-menu contract cleanup.
- **PR #42** remains a separate backend maintenance/worktree-hygiene lane.
- **PRs #41 / #43 / #36** remain frontend/annotate/Builder lanes.

So the next real parse-back-end slice should be:
- backend-only
- post-PR49
- adjacent to current compare/annotate helper surfaces
- explicitly zero-drift on route semantics

The strongest grounded next gap is the still-inline **lexeme notes + media/search HTTP cluster** in `python/server.py`.

## Current grounded evidence

### 1. The active frontend depends on this cluster directly
Current frontend consumers on `origin/main` include:
- `src/components/compare/CommentsImport.tsx`
  - uses `importCommentsCsv()` → `POST /api/lexeme-notes/import`
- `src/components/compare/LexemeDetail.tsx`
  - uses `saveLexemeNote()` → `POST /api/lexeme-notes`
  - uses `spectrogramUrl()` → `GET /api/spectrogram`
- `src/ParseUI.tsx`
  - uses `searchLexeme()` in the offset / candidate-search flow
- `src/components/annotate/LexemeSearchPanel.tsx`
  - also uses `searchLexeme()`

### 2. The backend route cluster is still inline in `python/server.py`
Current monolith locations on main:
- `_api_post_lexeme_note()` starts around `7227`
- `_api_post_lexeme_notes_import()` starts around `7270`
- `_api_get_spectrogram()` starts around `7414`
- `_api_get_lexeme_search()` starts around `7486`
- dispatch glue lives around:
  - `GET /api/spectrogram` + `GET /api/lexeme/search` near `6189-6194`
  - `POST /api/lexeme-notes` + `POST /api/lexeme-notes/import` near `6284-6289`

### 3. This surface has meaningful compatibility/validation rules worth freezing in tests
Examples visible in current code:
- `POST /api/lexeme-notes`
  - requires `speaker` and `concept_id`
  - supports delete semantics via `delete=true`
  - returns updated `lexeme_notes`
- `POST /api/lexeme-notes/import`
  - requires multipart upload
  - expects field name `csv`
  - validates `speaker_id`
  - enforces content-length and UTF-8 CSV decode rules
- `GET /api/spectrogram`
  - requires valid `speaker`
  - validates numeric `start` / `end`
  - resolves `audio` hint or derives fallback audio path
  - returns binary PNG with cache headers
- `GET /api/lexeme/search`
  - requires `speaker` and `variants`
  - validates `limit` and `max_distance`
  - supports optional `concept_id`, `language`, `tiers`
  - augments with cross-speaker/contact-variant signals when available

### 4. Coverage exists for lower layers, but not as a dedicated server-route bundle
Observed current coverage:
- algorithm/search unit coverage exists:
  - `python/test_lexeme_search.py`
- frontend/client consumers exist and are tested in places:
  - `CommentsImport.tsx`
  - `LexemeDetail.tsx`
  - `ParseUI.tsx`
- but there is **no dedicated** `python/test_server_lexeme_*.py` or `python/test_server_spectrogram*.py` route-level bundle on current main

That makes this a strong backend-owned next slice after PR #47.

## Source of truth

Primary backend sources:
- `python/server.py`
- `python/external_api/openapi.py`
- `python/test_external_api_surface.py`
- `python/test_lexeme_search.py`
- `src/api/client.ts` (read-only consumer contract)
- `src/components/compare/CommentsImport.tsx` (read-only consumer)
- `src/components/compare/LexemeDetail.tsx` (read-only consumer)
- `src/ParseUI.tsx` / `src/components/annotate/LexemeSearchPanel.tsx` (read-only consumers)
- `AGENTS.md`

## Specific task

Create **one fresh parse-back-end implementation PR** from the latest `origin/main` that extracts and hardens this lexeme/media/search HTTP contract.

### Required implementation direction

1. **Extract the lexeme-notes HTTP handlers from `python/server.py`.**
   For example into `python/app/http/lexeme_note_handlers.py` or an equivalent app-layer helper module:
   - write/delete single lexeme note
   - comments CSV import

2. **Extract the spectrogram + lexeme-search GET handlers from `python/server.py`.**
   For example into `python/app/http/media_search_handlers.py` or equivalent:
   - spectrogram route
   - lexeme search route

3. **Preserve all live contract behavior.**
   Explicitly keep current semantics unless a bug is proven:
   - multipart field names and validation rules
   - binary PNG response/content-type/cache headers
   - current query-param validation for search
   - current delete/update semantics for lexeme notes
   - current not-found / bad-request behavior for invalid speaker/audio resolution

4. **Add dedicated backend route-level tests.**
   Add direct helper tests and thin server-wrapper regressions proving at least:
   - lexeme note write/delete behavior
   - comments import happy path + missing csv / bad encoding / bad speaker failures
   - spectrogram validation and binary response behavior
   - lexeme search validation and success payload shape
   - OpenAPI stays honest if any implementation/spec drift is found

5. **Keep the task scoped to HTTP modularization + contract safety.**
   Do not rewrite the underlying lexeme-search algorithm or spectrogram renderer unless a real bug is uncovered during extraction.

## In scope

- `python/server.py`
- new app-layer HTTP helper module(s) for this cluster
- direct tests for those helpers
- thin server regression tests for:
  - `/api/lexeme-notes`
  - `/api/lexeme-notes/import`
  - `/api/spectrogram`
  - `/api/lexeme/search`
- narrowly required OpenAPI/test updates

## Out of scope

- PR #49 compute+offset HTTP task
- PR #48 Builder Actions-menu task
- PR #42 worktree hygiene
- frontend TypeScript / React changes
- broad search/spectrogram algorithm redesign
- UI changes

## Validation requirements

Run and report at least:
- targeted backend tests for the new lexeme/media/search HTTP bundle
- `python3 -m py_compile` for touched Python files
- `PYTHONPATH=python python3 -m pytest -q`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Reporting requirements

Open **one fresh parse-back-end implementation PR** from the latest `origin/main`.

In the PR body include:
- which route behaviors were preserved explicitly
- exact helper modules introduced
- any implementation/spec drift found and corrected
- confirmation of non-overlap with PRs `#49`, `#48`, `#42`, `#41`, `#43`, and `#36`
- exact tests run

## Academic / fieldwork considerations

- These routes support note-taking, candidate localization, and spectrographic inspection — all part of evidence-bearing linguistic analysis rather than disposable UI chrome.
- Silent drift here can corrupt the ergonomics of note provenance or search confidence without obvious crashes.
- Extracting and regression-locking this cluster improves auditability while preserving fieldwork behavior.