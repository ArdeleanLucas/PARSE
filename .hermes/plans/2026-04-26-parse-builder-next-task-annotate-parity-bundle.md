# parse-builder next task — decision import/export contract follow-up

## Goal

Ship **one fresh frontend-only Builder implementation PR** from current `origin/main` that fixes the still-incoherent **Decisions** import/export/load-save behavior in the React shell, using a canonical `parse-decisions` artifact instead of the current inconsistent enrichments dump / merge behavior.

## Why this is the right next task now

- PR **#41** already consumed the narrow `RegionManager` annotate parity slice.
- PR **#43** already consumed the remaining valid annotate offset-shell regression slice from the dirty `parse-builder-auto` WIP.
- That means the older Builder handoff must be refreshed again: if sent unchanged now, it would just resend work already in flight.
- The next grounded frontend-owned gap is the **Decisions** workflow itself.

Current `origin/main` still has visible contract drift in the shell:

1. **Actions menu → Save Decisions** does not save/export anything meaningful.
   - In `src/ParseUI.tsx`, the Actions-menu button only closes the menu.
2. **Right panel → Save decisions** exports the entire `enrichmentData` blob to `parse-decisions.json`.
   - That is not a clean canonical decisions artifact.
3. **Load decisions** is inconsistent.
   - one path points at `loadDecisionsRef`
   - the actual hidden input with `onChange` is `loadDecisionsMenuRef`
   - import currently calls `useEnrichmentStore.getState().save(data)` on the raw parsed JSON, which merges a whole payload into enrichments instead of replacing only the decisions-backed categories.
4. The local dirty Builder WIP still contains a plausible candidate helper:
   - `src/lib/decisionPersistence.ts`
   - plus an `enrichmentStore.replace()` addition
   - but this must be audited and salvaged selectively, not trusted blindly.

This lines up with the live plan doc and gives Builder a concrete, frontend-only next slice.

## Source of truth

Primary code + contract sources:
- current rebuild `origin/main`
- `src/ParseUI.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/stores/enrichmentStore.ts`
- `docs/plans/parseui-current-state-plan.md`

Relevant local salvage input only (not truth):
- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto`
  - `src/lib/decisionPersistence.ts`
  - `src/stores/enrichmentStore.ts`
  - any related `ParseUI` WIP only if still valid after audit

Oracle/live PARSE repo for UI intent if needed:
- `/home/lucas/gh/ardeleanlucas/parse`

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch for the next Builder implementation PR: current `origin/main`
- Current `origin/main`: `c5aee8b` (`fix(compare): bundle frontend contract hardening (#34)`)
- Open related lanes:
  - **PR #43** — annotate offset-shell regressions (already owns the prior remaining annotate-shell slice)
  - **PR #42** — parse-back-end worktree hygiene cleanup
  - **PR #44** — parse-back-end ORTH runtime contract reconciliation

### Live plan alignment

The current plan still says the decisions story needs unification / reconciliation, and this is now the clearest concrete frontend-owned version of that task.

### Concrete current-main evidence

In `src/ParseUI.tsx` today:
- Actions menu `Load Decisions` uses `loadDecisionsMenuRef.current?.click()`
- Actions menu `Save Decisions` just closes the menu
- Right-panel `Load decisions` uses `loadDecisionsRef.current?.click()`
- Right-panel `Save decisions` serializes full `enrichmentData` to `parse-decisions.json`
- the hidden JSON input parses the file and calls `useEnrichmentStore.getState().save(data)` directly

That is exactly the sort of inconsistent shell behavior this next Builder slice should correct.

## Specific task

Create **one fresh Builder implementation PR** from current `origin/main` that makes decisions import/export/load-save coherent.

### Required implementation direction

1. **Define one canonical exported decisions artifact.**
   - Prefer a dedicated `parse-decisions` payload rather than dumping all enrichments.
   - The local `parse-builder-auto/src/lib/decisionPersistence.ts` is a strong candidate salvage source.
   - Audit it against current shell behavior before keeping it.

2. **Unify Actions menu and Right-panel behavior.**
   - Both surfaces should invoke the same import/export handlers.
   - Remove the split ref / split behavior drift (`loadDecisionsRef` vs `loadDecisionsMenuRef`) unless both are truly needed and correctly wired.

3. **Make load semantics explicit and safe.**
   - Import should replace or rewrite only the decisions-backed categories it owns, not blindly merge arbitrary JSON into enrichments.
   - Preserve non-decision enrichments unless the canonical contract explicitly says otherwise.

4. **Audit whether `enrichmentStore.replace()` is justified.**
   - If the import path genuinely needs replace semantics, keep a minimal, tested `replace()` API.
   - If not, do not widen store surface area unnecessarily.

5. **Write regression tests.**
   At minimum cover:
   - Actions menu save actually exports the canonical decisions artifact
   - right-panel save/export uses the same canonical artifact
   - load decisions path uses the correct input/handler wiring
   - import rewrites only decisions-owned data correctly
   - stale top-level / legacy decision forms are handled intentionally if compatibility is required

## In scope

- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/parse/RightPanel.tsx` only if needed for wiring consistency
- `src/stores/enrichmentStore.ts` only if justified
- `src/lib/decisionPersistence.ts` if salvaged / created
- narrowly related docs/comments if needed

## Out of scope

- `python/*`
- parse-back-end PRs `#42` / `#44`
- annotate parity PRs `#41` / `#43`
- speculative redesign of the panel or Actions menu UI
- compute-mode semantics unless a tiny adjacent cleanup is required

## Validation requirements

Run and report at least:
- targeted `ParseUI` / decisions-related tests you add or update
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- browser smoke proving both Decisions entry points are wired

## Reporting requirements

Open **one fresh Builder implementation PR** from current `origin/main`.

In the PR body, include:
- the exact current-main decisions drift you found
- what was salvaged from `parse-builder-auto` vs discarded
- the canonical decisions artifact shape you chose
- confirmation that PRs `#43`, `#42`, and `#44` remained non-overlapping
- exact tests run

## Academic / fieldwork considerations

- Decision artifacts are comparative-analysis data, not disposable UI state.
- Exporting the whole enrichments blob as `parse-decisions.json` obscures provenance and makes downstream adjudication harder to reason about.
- A clean decisions contract improves reproducibility for cognate, flag, and borrowing adjudication workflows.
