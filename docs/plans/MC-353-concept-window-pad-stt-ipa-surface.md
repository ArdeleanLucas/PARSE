# MC-353 — STT/IPA action-menu pad selector parity

## Objective
Expose the existing action-menu audio context pad selector for STT-only and IPA-only concept-window / edited-only bulk runs, matching the backend pad support from PR #302 and preserving existing ORTH behavior from PR #301.

## Scope
- Frontend-only.
- Worktree: `/home/lucas/gh/worktrees/PARSE-rebuild/concept-window-pad-stt-ipa-surface`.
- Branch: `feat/concept-window-pad-stt-ipa-surface`.
- Target repo/base: `ArdeleanLucas/PARSE`, `main`.

## Files
- `src/components/shared/TranscriptionRunModal.tsx`
- `src/components/shared/__tests__/TranscriptionRunModal.test.tsx`
- `src/hooks/__tests__/useBatchPipelineJob.test.ts`

## Plan
1. Add RED tests for STT-only and IPA-only pad selector visibility in concept-window mode.
2. Add RED confirm-payload tests for STT-only and IPA-only selected pad values.
3. Add RED hidden-selector coverage for a non-pad-applicable step.
4. Add RED batch hook tests proving STT-only and IPA-only concept-window runs forward selected pad to every speaker.
5. Implement a generic `PAD_APPLICABLE_STEPS` predicate for `stt`, `ortho`, and `ipa`; keep full-mode hidden.
6. Rename local ORTH-specific pad state/ref/handler names to generic pad names without changing user-facing labels or test ids.
7. Validate focused tests, full Vitest, TypeScript, build, diff-check, and paranoid backend pytest.

## Completion criteria
- New modal tests fail on `origin/main` before implementation and pass after.
- Hook regressions document the already-generic batch payload path for STT-only and IPA-only pad forwarding.
- Existing ORTH-only path remains behavior-identical, including `action-menu-pad-0.0`, `action-menu-pad-0.2`, and `action-menu-pad-0.5` test ids.
- PR includes MC-353, RED/GREEN evidence, local validation, and CI status.
