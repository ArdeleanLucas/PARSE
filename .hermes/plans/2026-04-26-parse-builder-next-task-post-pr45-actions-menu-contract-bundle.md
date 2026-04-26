# parse-builder next task — post-PR45 Actions menu contract cleanup bundle

## Goal

Ship **one fresh frontend-only Builder implementation PR** from the latest `origin/main` _after the PR #45 compute-contract slice_ that reconciles the **remaining ParseUI Actions menu handlers** with the live typed-client/shared-helper contract, without redesigning the UI.

This is a shell-cleanup and regression-hardening task, not a UI re-imagining task.

## Why this is the right next task now

- **PR #36** remains the current Builder lane for the decisions contract slice.
- **PR #45** is now merged as the queued Builder successor handoff for compare compute semantics.
- Current `origin/main` already marks both **decisions** and **compute semantics** as done in `docs/plans/parseui-current-state-plan.md`.
- The same plan still leaves **§2 Actions menu contract reconciliation** as the next shell-cleanup item.

That makes the next grounded Builder-owned gap the **remaining Actions menu handler drift in `ParseUI.tsx`**.

## Current grounded evidence

### 1. The live plan still leaves Actions-menu reconciliation open
In `docs/plans/parseui-current-state-plan.md` on current `main`:
- §4 decisions story is marked **DONE**
- §5 compute semantics are marked **DONE**
- §2 still says:
  - normalize remaining ParseUI action handlers to the typed client surface where possible
  - avoid creating a second ad hoc API path in `ParseUI.tsx`

### 2. `ParseUI.tsx` still carries ad hoc Actions-menu logic that duplicates shared helpers
Current active-shell examples:
- `handleExportLingPy` in `src/ParseUI.tsx` manually calls `getLingPyExport()` and hand-rolls blob download logic
- the compare-side export helper already exists as `useExport()` and is already used by `src/components/compare/EnrichmentsPanel.tsx`
- `handleCustomListImport` in `src/ParseUI.tsx` owns its own prompt/import/summary path for concept-list tagging via `importTagCsv()`
- Actions-menu hidden input wiring for concept-list import still lives directly in `ParseUI.tsx`

This is exactly the sort of remaining shell-specific duplication §2 is pointing at.

### 3. Test coverage is still stronger on the right-panel path than on the Actions-menu path
Current tests already cover some adjacent behavior, for example:
- right-panel LingPy export from `ParseUI.test.tsx`
- comments-import modal opening from the right panel

But the Actions-menu equivalents are not yet locked down as thoroughly as the compute/decisions paths.

### 4. The UI must stay identical while the internals get cleaner
This is a good Builder task because it improves correctness and maintainability without changing the visible workstation layout.

## Source of truth

Primary active-shell sources:
- `docs/plans/parseui-current-state-plan.md`
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/hooks/useExport.ts`
- `src/hooks/__tests__/useExport.test.ts`
- `src/components/compare/EnrichmentsPanel.tsx`
- `src/api/client.ts`
- `AGENTS.md`

## Specific task

Create **one fresh Builder implementation PR** from the latest `origin/main` that normalizes the remaining Actions-menu handler contract.

### Required implementation direction

1. **Audit the remaining Actions-menu handlers in `ParseUI.tsx`.**
   Focus especially on:
   - LingPy export
   - concept-list/tag import wiring
   - any other remaining menu actions that still duplicate logic better owned by a shared helper/hook/component

2. **Prefer shared typed-client-backed helpers over ad hoc inline shell logic.**
   Examples:
   - if `handleExportLingPy` can be routed through `useExport()` cleanly, do that
   - if concept-list import needs a small shared helper or dedicated compare primitive instead of staying inline in `ParseUI.tsx`, extract it
   - do not add new bare `fetch()` calls or new duplicate API paths

3. **Keep behavior identical from the user’s perspective.**
   - same buttons
   - same dialogs/modals
   - same import/export affordances
   - no layout redesign

4. **Add regression tests specifically for the Actions-menu path.**
   At minimum cover whichever of these remain applicable after your audit:
   - Actions-menu LingPy export dispatches through the canonical export path
   - Actions-menu concept-list import triggers the intended typed-client/helper path
   - Actions-menu import/export buttons still close/open the correct UI affordances
   - existing right-panel paths remain non-regressed if you unify them behind shared handlers

5. **Keep the cleanup scoped.**
   This is not a broad rewrite of `ParseUI.tsx`; it is a contract cleanup for the remaining Actions-menu-specific drift.

## In scope

- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/hooks/useExport.ts` / tests if needed
- small new shared helper/hook/component only if justified by the audit
- narrowly related compare/shared files required to unify handler logic

## Out of scope

- current Builder task PR #36
- queued Builder compute-contract slice from PR #45
- parse-back-end lanes PR #47 / #42
- annotate parity work owned by PRs #41 / #43
- UI redesign or copy overhaul
- backend API changes

## Validation requirements

Run and report at least:
- targeted Actions-menu / export/import tests you add or update
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- browser smoke if production UI wiring changes

## Reporting requirements

Open **one fresh Builder implementation PR** from the latest `origin/main`.

In the PR body include:
- which Actions-menu handlers were still ad hoc on current main
- what shared helper(s) or paths you normalized them to
- confirmation that visible UI behavior stayed the same
- confirmation of non-overlap with PRs `#36`, `#45`, `#47`, `#42`, `#41`, and `#43`
- exact tests run

## Academic / fieldwork considerations

- The Actions menu is operational glue for real fieldwork workflows: imports, exports, batch jobs, and adjudication artifacts.
- Keeping those handlers aligned with the canonical typed-client/shared-helper contract reduces silent drift between superficially similar UI affordances.
- This improves reproducibility without changing the visible research workstation.