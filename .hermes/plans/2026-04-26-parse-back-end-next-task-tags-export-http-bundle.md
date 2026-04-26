# parse-back-end next task — tags and export HTTP handler bundle

## Goal

Ship **one larger backend-only follow-up PR** that extracts the remaining tag + export HTTP cluster from `python/server.py` into application-layer helpers, while preserving request/response behavior exactly so the React UI can remain identical to the original PARSE workstation.

## Why this is the right next task now

- Lucas explicitly wants **longer tasks**, because writing tiny prompt PRs now costs more than the implementation slices themselves.
- The previous backend bundle just landed on current `main`:
  - `70f9783` — `refactor(config): extract config and CSV import HTTP handlers (#33)`
- That extraction created the current pattern and adjacent stopping point:
  - `python/app/http/project_config_handlers.py`
  - `python/test_app_http_project_config_handlers.py`
  - thin server-wrapper regressions for the extracted config/import routes
- The next coherent inline cluster in `python/server.py` is the **tags + export** surface:
  - `GET /api/tags`
  - `POST /api/tags/merge`
  - `GET /api/export/lingpy`
  - `GET /api/export/nexus`
- This is a good next backend bundle because it is:
  - large enough to justify one real task
  - adjacent in the server monolith
  - contract-sensitive but frontend-non-overlapping
  - safely separate from Builder’s frontend compare bundle

## Hard boundary

- **Do not touch UI design.**
- Builder owns the frontend/UI lane.
- Your job is backend-only contract preservation: the UI should not need to change because of this refactor.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch: current `origin/main`
- Current `origin/main`: `70f9783` (`refactor(config): extract config and CSV import HTTP handlers (#33)`)
- Builder queue to avoid overlapping with:
  - PR #32 — Builder compare contract bundle handoff
  - frontend implementation PRs #27, #29, #31 may still be in flight

### Current inline backend cluster in `python/server.py`
At handoff time, these handlers remain inline:
- `def _api_get_tags(self) -> None:` around line `7629`
- `def _api_post_tags_merge(self) -> None:` around line `7645`
- `def _api_get_export_lingpy(self) -> None:` around line `7704`
- `def _api_get_export_nexus(self) -> None:` around line `7730`

### Existing pattern to follow
Use the same behavior-preserving extraction style as the already-landed backend modules:
- `python/app/http/auth_handlers.py`
- `python/app/http/job_observability_handlers.py`
- `python/app/http/external_api_handlers.py`
- `python/app/http/project_config_handlers.py`

That means:
1. new helper module under `python/app/http/`
2. thin `server.py` wrappers only
3. direct app-layer tests for the helper logic
4. thin server-wrapper regressions for route preservation
5. no client-contract drift

## Specific task

Create **one fresh parse-back-end implementation PR** from current `origin/main` that extracts the tag + export cluster into application-layer helpers.

### Recommended module shape
- `python/app/http/project_artifact_handlers.py`

If you find a better narrow name like `tags_export_handlers.py`, that is fine — keep the scope explicit.

### Required implementation direction
1. **Extract tag read/write handlers.**
   - Move `GET /api/tags` logic out of `server.py`.
   - Move `POST /api/tags/merge` logic out of `server.py`.
   - Preserve exact JSON response shapes and merge semantics.

2. **Extract export download handlers.**
   - Move `GET /api/export/lingpy` into the helper module.
   - Move `GET /api/export/nexus` into the helper module.
   - Preserve generated payload semantics, content types, attachment filenames, and download behavior.

3. **Add direct helper tests.**
   - Cover tag file absent / tag file malformed / merge success / merge validation errors.
   - Cover LingPy export response metadata and content handoff.
   - Cover NEXUS export response metadata and deterministic matrix/header behavior on representative fixtures.

4. **Keep thin wrapper regressions.**
   - Add or update server-level tests so the route wrappers clearly delegate to the new helper module.
   - Update external API surface tests only if route registration or operation metadata is mechanically touched.

5. **Preserve behavior exactly.**
   - If you discover a real pre-existing bug, isolate it carefully and call it out explicitly instead of silently changing semantics.

## Non-negotiable behavior rules

### `GET /api/tags`
- Keep response wrapper `{ "tags": [...] }`.
- If `parse-tags.json` is absent, still return `{ "tags": [] }` with `200`.
- Preserve current malformed-file fallback / error behavior.

### `POST /api/tags/merge`
- Preserve additive merge semantics into `parse-tags.json`.
- Preserve validation that `tags` must be an array.
- Preserve response shape `{ "ok": True, "tagCount": <N> }`.
- Preserve label/color/default concept merge behavior.

### `GET /api/export/lingpy`
- Preserve the LingPy TSV payload generation path.
- Preserve headers including content type and download filename.
- Preserve current temporary-file cleanup behavior.

### `GET /api/export/nexus`
- Preserve the current NEXUS matrix semantics:
  - `1` = in cognate group
  - `0` = has form but different group
  - `?` = missing / unreviewed
- Preserve override precedence, deterministic ordering, content type, and download filename.

## In scope

- `python/server.py`
- new `python/app/http/project_artifact_handlers.py` (or equivalently narrow module)
- `python/app/http/__init__.py`
- new direct helper tests
- server wrapper regressions for the touched routes
- `python/test_external_api_surface.py` only if mechanically needed

## Out of scope

- frontend/UI files under `src/`
- CLEF/contact-lexeme routes
- config/import handlers already extracted in PR #33
- auth/job-observability/external-API slices already extracted
- behavior changes that would require frontend adaptation

## Validation requirements

Run and report at least:
- direct tests for the new helper module
- `pytest python/test_server_tags_import.py -q` (adjacent tag behavior guard)
- server-level tests you add/update for `GET /api/tags`, `POST /api/tags/merge`, `GET /api/export/lingpy`, `GET /api/export/nexus`
- `pytest python/test_external_api_surface.py -q` if route dispatch or docs registration is touched
- `python3 -m py_compile python/server.py python/app/http/*.py`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

### Rebuild-worktree note
If this worktree lacks frontend dependencies, use the known rebuild-lane workaround:
- temporarily symlink `node_modules` from `/home/lucas/gh/ardeleanlucas/parse/node_modules`
- remove the symlink after validation

## Reporting requirements

Open **one fresh parse-back-end implementation PR** from current `origin/main`.

In the PR body, include:
- exact endpoints extracted
- confirmation that response shapes / headers / download behavior were preserved
- any pre-existing bug discovered versus any intentional behavior change
- exact tests run

## Academic / fieldwork considerations

- Tags and exports are not cosmetic; they shape analytical overlays and downstream comparative data products.
- LingPy and NEXUS exports feed downstream historical-linguistics workflows, so silent drift here can corrupt reproducibility.
- This bundle should optimize for **contract stability, deterministic output, and reproducible export behavior**, not clever refactoring for its own sake.
