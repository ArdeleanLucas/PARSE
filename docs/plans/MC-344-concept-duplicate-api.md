# MC-344 — Concept duplicate API for A/B variants

## Objective
Add a backend-only endpoint that splits one `concepts.csv` row into adjacent A/B semantics for frontend variant tracking:

`POST /api/concepts/{conceptId}/duplicate`

The endpoint touches `concepts.csv` only. It does not mutate annotations, tags, enrichments, survey overlap, or speaker data.

## Grounded investigation
- Canonical five-column CSV helpers already live in `python/concept_source_item.py`:
  - `CONCEPT_FIELDNAMES = (id, concept_en, source_item, source_survey, custom_order)`
  - `read_concepts_csv_rows(path)` leniently normalizes legacy/two-column rows
  - `write_concepts_csv_rows(path, rows, atomic=True)` writes `concepts.csv.tmp`, fsyncs, and replaces the destination
- Existing full-file concept import route is `_api_post_concepts_import` in `python/server_routes/exports.py`; server route modules are installed from `_ROUTE_MODULE_NAMES` in `python/server.py`.
- `python/server.py` currently has 2001 physical lines and `test_server_route_modularization.py` enforces `<2005`, so dispatch changes must be extremely small or moved out of `server.py`.
- OpenAPI routes are declared in `python/external_api/openapi.py`; `python/test_external_api_surface.py::test_build_openapi_document_covers_the_current_http_route_surface` asserts the exact path set.
- Concept readers that the frontend/AI calls are disk-backed and uncached:
  - `python/app/services/workspace_config.py::_load_concepts` reads `concepts.csv` on each config build.
  - `python/ai/tools/contact_lexeme_tools.py::load_project_concepts` reads `concepts.csv` on each tool call.
  Therefore the duplicate endpoint does not need an explicit cache invalidation hook; a subsequent `/api/config` or tool read sees the new `(B)` row immediately.

## Implementation plan
1. Add RED tests in `python/test_concept_duplicate_endpoint.py` for:
   - success: original `X` becomes `X (A)`, new `X (B)` uses max numeric id + 1, source fields are preserved, custom_order is empty, backup is byte-identical.
   - 409 when the target row already ends in `(A)`.
   - 409 when the target row already ends in `(B)`.
   - 409 when a `(B)` sibling already exists with the same `source_item`.
   - 404 for missing concept id.
   - 400 for nonnumeric id.
   - restore-on-atomic-write failure leaves `concepts.csv` equal to the backup.
   - response payload shape is exactly `{primary, sibling}`.
2. Add OpenAPI RED coverage in `python/test_external_api_surface.py` for `/api/concepts/{conceptId}/duplicate` including request body, responses, and `x-parse.idempotent = false`.
3. Implement `python/concepts_io.py`:
   - `ConceptDuplicateError(status, message)`
   - `duplicate_concept_ab_pair(project_root, concept_id, *, now=None)`
   - helper suffix detection and sibling conflict detection.
   - backup filename `concepts.csv.bak-<UTC-iso>-pre-duplicate-<srcId>`.
   - write via `write_concepts_csv_rows(..., atomic=True)`, with backup restore on `OSError`/CSV write failures.
4. Add `_api_post_concept_duplicate` to `python/server_routes/exports.py`, mapping helper errors to `ApiError` and returning 200 JSON.
5. Add compact `server.py` dispatch for `/api/concepts/{id}/duplicate` and malformed `/api/concepts/*` POSTs.
6. Update OpenAPI schema in `python/external_api/openapi.py` and exact path-set test.
7. Validate targeted and full backend gates, plus isolated manual smoke in a temp workspace. Do not touch `/home/lucas/parse-workspace`.

## Validation commands
```bash
PYTHONPATH=python PARSE_TAGS_PATH=/tmp/parse-tags-pytest-concept-dup.json BLOCK_LIVE_PROCESS_ISOLATION=1 python3 -m pytest -q python/test_concept_duplicate_endpoint.py python/test_external_api_surface.py python/test_server_route_modularization.py
uvx ruff check python/ --select E9,F63,F7,F82
PYTHONPATH=python PARSE_TAGS_PATH=/tmp/parse-tags-pytest-concept-dup.json BLOCK_LIVE_PROCESS_ISOLATION=1 python3 -m pytest python -q
npm run build
```

If `node_modules/` is absent in the worktree, use the canonical repo symlink temporarily and remove it before commit.
