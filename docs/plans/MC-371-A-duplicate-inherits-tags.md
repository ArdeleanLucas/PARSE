# MC-371-A — Duplicate inherits tag memberships across both tag layers

## Objective
Ensure `POST /api/concepts/{conceptId}/duplicate` mirrors tag membership from the duplicated primary concept id to the new sibling id in both PARSE tag storage layers:

1. Per-speaker annotation `concept_tags` maps in `annotations/*.json` (already implemented, keep covered).
2. Global `python/storage/tags_store.py` tag vocabulary entries where each tag has a `concepts` list.

Also refresh the React tag store after the duplicate/config reload path so tag-management views see the updated global memberships.

## Scope
- Backend: `python/server_routes/exports.py`, `python/test_concept_duplicate_endpoint.py`.
- Frontend: `src/ParseUI.tsx`, `src/ParseUI.test.tsx`.
- Docs: latest rolling changes/report doc if clearly identifiable.
- No live server, browser, screenshots, `parse-run`, or Vite dev server.

## Plan
1. Write RED backend tests for global tag membership mirror, idempotency/deduplication, best-effort failure swallowing with warning, and no-write fast path.
2. Run the new backend nodeids and confirm expected failures on current `origin/main` behavior.
3. Implement `_mirror_global_tag_concepts_to_sibling(primary_id, sibling_id)` in `python/server_routes/exports.py`, using `tags_store.fetch_all()` and `tags_store.replace_all()` only, logging/swallowing `OSError` and `TagValidationError`.
4. Invoke the mirror immediately after `_copy_concept_tags_to_sibling` and before duplicate response send.
5. Extend an existing ParseUI duplicate-success test to assert `syncFromServer` runs after duplicate/config reload; then add `await syncTagStoreFromServer()` after `await reloadConfig()` in the handler.
6. Add a one-line docs note to the latest rolling PR refresh report if it remains the obvious rolling-changes doc.
7. Validate with focused pytest/Vitest first, then required gates: backend pytest, ruff, Vitest, TypeScript, build, and `git diff --check`.
8. Commit with `[MC-371-A]`, push, open one PR against `ArdeleanLucas/PARSE:main`, verify base/status/CI.

## Completion criteria
- Four new backend tests pass and existing duplicate endpoint suite remains green.
- Extended `src/ParseUI.test.tsx` duplicate handler test passes.
- Required lint/test/build gates pass.
- PR title: `[MC-371-A] fix(concepts): duplicate mirrors tag membership across both layers`.
- PR body first line: `**MC Task:** MC-371 — Duplicate lexeme button broken in UI / Lane MC-371-A`.
