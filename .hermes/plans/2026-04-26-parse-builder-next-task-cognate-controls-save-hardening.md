# parse-builder next queued task — CognateControls save-path hardening

## Goal

Harden `src/components/compare/CognateControls.tsx` so its cognate-set persistence path matches the current React store reality, while keeping the React UI visually identical to the original and avoiding any UI re-imagining.

## Why this is the right next task now

- Current rebuild `origin/main` is `0d78bb8` (`test(compare): harden compute semantics regressions (#28)`).
- PR #27 is the active Builder implementation lane (`https://github.com/TarahAssistant/PARSE-rebuild/pull/27`) implementing the typed-client cleanup for `BorrowingPanel`.
- PR #26 is already the next queued Builder handoff (`https://github.com/TarahAssistant/PARSE-rebuild/pull/26`) for `configStore.update()` parity.
- parse-back-end remains on PR #23 (`https://github.com/TarahAssistant/PARSE-rebuild/pull/23`), so the next Builder slice should remain frontend-only.
- On current main, `src/components/compare/CognateControls.tsx` still contains a stale fallback path:
  - `catch { /* enrichmentStore.save not yet implemented — store locally */ }`
- That comment and fallback are now wrong because `src/stores/enrichmentStore.ts::save()` is implemented and persists immediately.

## Hard UI constraint

- **Do not re-imagine the UI.**
- React PARSE UI should remain visually identical to the original UI.
- This slice is about save-path correctness and regression coverage, not a redesign.
- Keep any visible UI changes at zero unless a tiny, necessary error surface is unavoidable; if you think one is needed, keep it minimal and explain why in the PR.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch: `origin/main`
- Current head: `0d78bb8`
- Current Builder chain:
  - PR #27 — active implementation: `https://github.com/TarahAssistant/PARSE-rebuild/pull/27`
  - PR #26 — queued next: `https://github.com/TarahAssistant/PARSE-rebuild/pull/26`
- parse-back-end queue:
  - PR #23 — `https://github.com/TarahAssistant/PARSE-rebuild/pull/23`

### Relevant current-main files
- `src/components/compare/CognateControls.tsx`
  - saves `manual_overrides.cognate_sets`
  - still swallows save errors with an obsolete comment implying store persistence is missing
  - still calls `onGroupsChanged?.(...)` after the swallowed failure path
- `src/stores/enrichmentStore.ts`
  - `save()` is implemented and persists through `saveEnrichments(...)`
- `src/components/compare/CognateControls.test.tsx`
  - currently covers placeholder/render/merge/split/cycle basics
  - does **not** cover persistence-success or persistence-failure semantics

## Specific task

Make `CognateControls` truthful and robust about persistence without redesigning the UI.

### Required implementation direction
1. Remove the obsolete `enrichmentStore.save not yet implemented` fallback assumption.
2. Decide and implement the correct persistence semantics for save failure, for example:
   - do not falsely treat a failed save as persisted success
   - do not leave misleading dead code/comments that imply local fallback exists when it does not
3. Add regression tests for:
   - successful save path updates `manual_overrides.cognate_sets`
   - failure path behavior is explicit and deterministic
4. Preserve the existing visual UI and interaction model unless a minimal error signal is strictly necessary.

## In scope
- `src/components/compare/CognateControls.tsx`
- `src/components/compare/CognateControls.test.tsx`
- adjacent compare/store typings only if narrowly required

## Out of scope
- `python/server.py`
- parse-back-end PR #23
- Builder PR #27 BorrowingPanel typed-client work
- Builder PR #26 configStore parity work
- any compare-panel redesign or chrome reshaping

## Validation requirements
Run and report at least:
- `npm run test -- --run src/components/compare/CognateControls.test.tsx`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Academic / UX considerations
- Cognate adjudication is core comparative data, not auxiliary UI state.
- A silent failed save risks misleading downstream linguistic interpretation.
- The workstation should stay visually stable while the persistence semantics become more honest.

## Reporting requirements
Open a fresh implementation PR from current `origin/main` **after** PR #27 and PR #26 unless Lucas explicitly resequences the queue.

In the PR body, include:
- the obsolete fallback removed
- the chosen failure semantics
- confirmation that UI appearance stayed aligned with the original / no re-imagining
- exact tests run
