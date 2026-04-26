# parse-back-end next task — CLEF contact/config/catalog HTTP handler bundle

## Goal

Ship **one larger backend-only follow-up PR** that extracts the remaining CLEF/contact-language HTTP cluster from `python/server.py` into application-layer helpers, while preserving response shapes and semantics exactly so the frontend can stay visually identical to the canonical PARSE workstation.

## Why this is the right next task now

- Lucas explicitly wants **longer tasks**, because coordinator time spent writing tiny prompt PRs now exceeds the cost of the tiny implementation slices.
- Current backend sequencing is now cleanly staged:
  - merged PR #33 extracted config/import handlers
  - queued PR #35 covers the tags/export handler bundle
- The next coherent inline backend cluster after PR #35 is the **CLEF contact/config/catalog** surface:
  - contact-language coverage
  - CLEF config read/write
  - form selection persistence
  - catalog/provider lookup
  - provenance/sources reporting
- This is a good next bundle because it is:
  - large enough to justify one real parse-back-end task
  - tightly related as one backend concern
  - adjacent in `python/server.py`
  - non-overlapping with Builder’s frontend-only work

## Hard boundary

- **Do not touch UI design.**
- Builder owns the frontend/UI parity lane.
- Your job is backend-only contract preservation: the React UI should not need to change because of this refactor.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch for the future implementation PR: current `origin/main`
- Current `origin/main`: `70f9783` (`refactor(config): extract config and CSV import HTTP handlers (#33)`)
- Immediate parse-back-end task ahead of this one:
  - PR #35 — tags/export bundle handoff
- Frontend lanes to avoid overlapping with:
  - PR #34 — `fix(compare): bundle frontend contract hardening`
  - PR #36 — queued Builder UI parity bundle

### Current inline backend cluster in `python/server.py`
At handoff time, these handlers remain inline:
- `def _api_get_contact_lexeme_coverage(self) -> None:` around line `7911`
- `def _api_get_clef_config(self) -> None:` around line `7944`
- `def _api_post_clef_config(self) -> None:` around line `7989`
- `def _api_post_clef_form_selections(self) -> None:` around line `8074`
- `def _api_get_clef_catalog(self) -> None:` around line `8152`
- `def _api_get_clef_providers(self) -> None:` around line `8197`
- `def _api_get_clef_sources_report(self) -> None:` around line `8204`

### Existing extraction pattern to follow
Use the same behavior-preserving extraction style as the already-landed backend modules:
- `python/app/http/auth_handlers.py`
- `python/app/http/job_observability_handlers.py`
- `python/app/http/external_api_handlers.py`
- `python/app/http/project_config_handlers.py`

That means:
1. new helper module(s) under `python/app/http/`
2. thin `server.py` wrappers only
3. direct app-layer tests for helper logic
4. thin server-wrapper regressions for route preservation
5. no client-contract drift

## Specific task

Create **one fresh parse-back-end implementation PR** from current `origin/main` after PR #35 that extracts the CLEF/contact-language HTTP cluster into application-layer helpers.

### Recommended module shape
- `python/app/http/clef_http_handlers.py`

If you find that two narrowly named modules are cleaner without splitting the task too finely, that is acceptable — keep the bundle coherent.

### Required implementation direction
1. **Extract coverage + config read/write handlers.**
   - Move `GET /api/contact-lexemes/coverage` out of `server.py`.
   - Move `GET /api/clef/config` out of `server.py`.
   - Move `POST /api/clef/config` out of `server.py`.
   - Preserve exact response fields, validation rules, and config merge semantics.

2. **Extract persisted form-selection handler.**
   - Move `POST /api/clef/form-selections` out of `server.py`.
   - Preserve normalization, deduplication, and `_meta.form_selections` persistence semantics exactly.

3. **Extract catalog/provider/report read handlers.**
   - Move `GET /api/clef/catalog` out of `server.py`.
   - Move `GET /api/clef/providers` out of `server.py`.
   - Move `GET /api/clef/sources-report` out of `server.py`.
   - Preserve catalog override merging, provider ordering, and provenance-report shape exactly.

4. **Add direct helper tests.**
   Cover at minimum:
   - coverage payload shape on representative config data
   - `GET /api/clef/config` configured/unconfigured states
   - `POST /api/clef/config` validation + preservation of existing concepts / form selections
   - `POST /api/clef/form-selections` validation + normalization + persistence
   - catalog extras merge behavior
   - provider ordering output
   - provenance/sources report shape on representative config fixtures

5. **Keep thin wrapper regressions.**
   - Add or update server-level tests proving the wrappers delegate to the new helpers.
   - Update `python/test_external_api_surface.py` only if route registration or OpenAPI-facing metadata is mechanically touched.

6. **Preserve behavior exactly.**
   - If you discover a real pre-existing bug or ambiguity, isolate it carefully and call it out explicitly instead of silently changing semantics.

## Non-negotiable behavior rules

### `GET /api/contact-lexemes/coverage`
- Preserve the current `{ "languages": ... }` response shape.
- Preserve the meaning of `total`, `filled`, `empty`, and per-language `concepts` payloads.

### `GET /api/clef/config`
- Preserve fields:
  - `configured`
  - `primary_contact_languages`
  - `languages`
  - `config_path`
  - `concepts_csv_exists`
  - `meta`
- Preserve language sorting and script/family handling.

### `POST /api/clef/config`
- Preserve validation that `primary_contact_languages` must be a list.
- Preserve the current limit of at most 2 primary contact languages.
- Preserve the behavior that existing per-language `concepts` data is kept.
- Preserve the behavior that existing `_meta.form_selections` survives config re-saves.
- Preserve response shape:
  - `success`
  - `config_path`
  - `primary_contact_languages`
  - `language_count`

### `POST /api/clef/form-selections`
- Preserve validation for `concept_en`, `lang_code`, and `forms`.
- Preserve lowercasing / normalization of `lang_code`.
- Preserve deduplication and trimming of `forms`.
- Preserve write location in `_meta.form_selections`.
- Preserve response shape:
  - `success`
  - `concept_en`
  - `lang_code`
  - `forms`

### `GET /api/clef/catalog`
- Preserve merge behavior with `config/sil_catalog_extra.json`.
- Preserve sorting and response shape `{ "languages": [...] }`.

### `GET /api/clef/providers`
- Preserve provider priority ordering from `compare.providers.registry.PROVIDER_PRIORITY`.
- Preserve response shape `{ "providers": [...] }`.

### `GET /api/clef/sources-report`
- Preserve provenance aggregation semantics and response shape.
- Preserve compatibility with both legacy and newer provenance representations.
- Preserve deterministic, citation-friendly output structure.

## In scope

- `python/server.py`
- new helper module(s) under `python/app/http/`
- `python/app/http/__init__.py`
- new direct helper tests
- server-wrapper regressions for the touched routes
- `python/test_external_api_surface.py` only if mechanically needed

## Out of scope

- frontend/UI files under `src/`
- tags/export routes already queued in PR #35
- auth/job-observability/external-API/config-import slices already handled elsewhere
- compute algorithm changes inside the CLEF fetcher/providers
- any API change that would require frontend adaptation

## Validation requirements

Run and report at least:
- direct tests for the new CLEF helper module(s)
- server-level tests you add/update for the touched CLEF/contact endpoints
- `pytest python/test_external_api_surface.py -q` if route dispatch or docs registration is touched
- relevant existing adjacent tests if touched indirectly (for example provider/fetcher tests)
- `python3 -m py_compile python/server.py python/app/http/*.py`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

### Rebuild-worktree note
If this worktree lacks frontend dependencies, use the known rebuild-lane workaround:
- temporarily symlink `node_modules` from `/home/lucas/gh/ardeleanlucas/parse/node_modules`
- remove the symlink after validation

## Reporting requirements

Open **one fresh parse-back-end implementation PR** from current `origin/main` after PR #35.

In the PR body, include:
- exact endpoints extracted
- confirmation that response shapes / validation / persistence behavior were preserved
- any pre-existing bug or ambiguity discovered versus any intentional behavior change
- exact tests run

## Academic / fieldwork considerations

- CLEF config and provenance routes shape how borrowing/reference evidence is configured, persisted, and later interpreted in comparative analysis.
- Silent drift here can distort scholarly traceability, provider provenance, or user selections that guide comparative judgment.
- This bundle should optimize for **contract stability, reproducible provenance, and preservation of linguistic review state**, not architectural cleverness.
