# MC-352 ORTH action-menu pad parity frontend

## Objective
Add the same 0.0 / 0.2 default / 0.5 pad selector used by per-lexeme rerun dialogs to ORTH bulk action-menu compute flows, and always send the selected pad in the compute-start request body.

## Scope
- Base: `origin/main` in canonical `ArdeleanLucas/PARSE` worktree branch `feat/orth-action-menu-pad-parity-frontend`.
- Frontend only: TypeScript API contract, action-menu UI, Vitest tests.
- ORTH bulk concept-window actions only: Run all concepts, Run edited concepts, Run ORTH where they drive ORTH compute.
- Out of scope: IPA bulk UI, full pipeline/full-file, forced alignment/boundaries/offset/retranscribe, per-lexeme dialog, persistence.

## Plan
1. Locate compute-start API contract and ORTH action-menu confirmation component/tests.
2. Add RED tests for API `pad` pass-through and UI pad selector render/selection/reset/keyboard behavior.
3. Reuse `LEXEME_RERUN_PAD_VALUES` and `LexemeRerunPad`; add a compute alias only if useful.
4. Wire selected pad into ORTH bulk compute payloads and preview labels; reset to 0.2 on open/close.
5. Validate with focused Vitest, full Vitest, `tsc --noEmit`, build, pytest, diff-check.
6. Open PR on `ArdeleanLucas/PARSE` referencing MC-352 and the handoff.

## Completion criteria
- Six requested tests fail on `origin/main` before implementation and pass after.
- Local validation gates pass.
- PR includes MC-352, validation evidence, backend parity note, and modified action-menu file paths.
