# MC-371-C Delete Variant Plan

## Objective
Make deleting a single concept variant a first-class PARSE action: `DELETE /api/concepts/{conceptId}` with annotation-safety checks, sidecar cleanup, OpenAPI coverage, and the right-click UI/contract needed to invoke it.

## Scope
- Backend: `python/concepts_io.py`, `python/server_routes/exports.py`, `python/server.py`, `python/external_api/openapi.py`, backend tests.
- Frontend contract/UI: `src/api/contracts/concepts.ts`, `src/components/parse/ConceptSidebar.tsx`, `src/ParseUI.tsx`, focused Vitest tests.
- Keep bottom-right Toast render for warnings/errors only; remove duplicate success toast call.

## Steps
1. Inspect duplicate/delete-survey-link seams and current tests.
2. Add failing backend tests for delete success, 409 blockers, sidecar cleanup, rollback, 404, and partial sidecars.
3. Implement delete helper, route handler, route dispatch, sidecar cleanup, and OpenAPI contract.
4. Add failing frontend tests for contract, context-menu delete visibility/callback, duplicate-success no-toast, and delete modal success/conflict flows.
5. Implement frontend contract/menu/modal wiring.
6. Run targeted tests, full backend/frontend gates, ruff, tsc, build, and diff checks.
7. Commit, push, open PR against `ArdeleanLucas/PARSE` `main`, verify base/status, and close out MC/daily logs.

## Completion Criteria
- `DELETE /api/concepts/{id}` refuses annotated concepts with 409 plus `blocking_speakers`.
- Unannotated deletes remove the CSV row with backup/rollback safety and best-effort sidecar cleanup.
- OpenAPI exposes `deleteConcept`.
- Right-click Delete appears on child/singleton rows, not grouped parent rows.
- Child variant context-menu handler stops propagation defensively.
- Duplicate success no longer calls `setDuplicateToast({ variant: 'success' })`.
