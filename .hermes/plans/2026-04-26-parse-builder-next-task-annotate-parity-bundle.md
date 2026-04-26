# parse-builder next task — post-PR41 annotate shell follow-up

## Goal

Ship **one fresh frontend-only Builder implementation PR** from current `origin/main` that recovers the remaining valid annotate-shell work **not already consumed by PR #41**, while keeping the rebuild aligned with the oracle/live PARSE React workstation and avoiding any UI re-imagining.

## Why this is the right next task now

- Builder now has an active narrow annotate parity slice in **PR #41**:
  - `fix(annotate): restore oracle region decision storage`
- That means the older broader annotate-parity handoff must be refreshed so it becomes a **genuinely new task**, not a stale re-send of work already underway.
- There is also **local dirty Builder WIP** in:
  - `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto`
- That WIP strongly suggests there is still a meaningful remaining frontend slice after PR #41, especially around:
  - `src/ParseUI.tsx`
  - `src/ParseUI.test.tsx`
  - potential decision-persistence helper work
- The next coherent Builder task is therefore:
  - audit the remaining non-RegionManager annotate-shell / decision-persistence follow-up
  - recover only the valid parts on a fresh branch from current `origin/main`
  - keep strict non-overlap with PR #41

## Hard UI constraint

- **Do not redesign the UI.**
- **Do not modernize the UI for its own sake.**
- **Do not rename, regroup, or restyle controls unless matching the canonical/oracle UI requires it.**
- Visible changes are allowed only when they correct drift back toward the canonical PARSE interface.

## Source of truth

Primary oracle/live repo:
- `/home/lucas/gh/ardeleanlucas/parse`

Audit against the current live React surfaces there, especially:
- `src/ParseUI.tsx`
- relevant `src/components/annotate/*`
- any current decision import/export behavior exposed through the unified shell

Secondary local Builder-WIP reference (for salvage only, **not** truth):
- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto`

Treat `parse-builder-auto` as a source of candidate changes to inspect, **not** as automatically correct code.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch for your next implementation PR: current `origin/main`
- Current `origin/main`: `c5aee8b` (`fix(compare): bundle frontend contract hardening (#34)`)
- Open related lanes:
  - **PR #41** — active narrow annotate parity slice (`RegionManager` only)
  - **PR #42** — parse-back-end worktree hygiene cleanup (do not overlap)
- Current Builder docs handoff PR:
  - **PR #36** — this PR, refreshed in place to the new remaining task

### Critical non-overlap rule

**Do not overlap PR #41.**

PR #41 already owns:
- `src/components/annotate/RegionManager.tsx`
- `src/components/annotate/RegionManager.test.tsx`
- oracle parity for annotate prior-region decision storage

Assume the RegionManager slice is already spoken for.

### Dirty local Builder WIP worth auditing

The current local Builder auto worktree contains unresolved/dirty state:
- `docs/plans/parseui-current-state-plan.md`
- `src/ParseUI.test.tsx`
- `src/ParseUI.tsx` (conflicted)
- `src/components/annotate/RegionManager.test.tsx`
- `src/components/annotate/RegionManager.tsx`
- `src/lib/decisionPersistence.ts`
- `src/stores/enrichmentStore.ts`

Interpretation:
- the **RegionManager** files are now mostly superseded by PR #41
- the **remaining potentially valuable follow-up** is likely in:
  - `src/ParseUI.tsx`
  - `src/ParseUI.test.tsx`
  - possibly `src/lib/decisionPersistence.ts`
  - possibly `src/stores/enrichmentStore.ts`

But you must **re-audit those files from scratch** against oracle + current contract before keeping any of them.

## Specific task

Create **one fresh Builder implementation PR** from current `origin/main` that recovers the valid remaining non-RegionManager work.

### Required implementation direction

1. **Inspect PR #41 first.**
   - Read the live PR body and changed files.
   - Treat that slice as already owned.

2. **Audit the remaining dirty local Builder WIP as salvage input only.**
   - Inspect `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto`.
   - Identify what is still useful after carving out the PR #41 RegionManager work.
   - Do not just force-finish or blindly commit the dirty worktree.

3. **Recover the next valid frontend-only slice on a fresh branch.**
   Focus especially on:
   - `src/ParseUI.tsx`
   - `src/ParseUI.test.tsx`
   - optionally `src/lib/decisionPersistence.ts`
   - optionally `src/stores/enrichmentStore.ts`

4. **Be strict about the decisions story.**
   - If the `decisionPersistence` helper is genuinely required by the current canonical shell behavior, keep it and test it.
   - If it conflicts with oracle behavior or with the live PR #41 region-decision semantics, drop or narrow it.
   - Do not introduce a second contradictory persistence story.

5. **Stay frontend-only and non-overlapping.**
   - no backend files under `python/`
   - no worktree-cleanup changes (parse-back-end owns PR #42)
   - no redoing RegionManager parity already in PR #41 unless a tiny dependency adjustment is unavoidable and explicitly justified

## In scope

- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- narrow adjacent frontend helpers/stores if required by the recovered slice
- annotate-shell / unified-shell decision behavior only if justified by current oracle + rebuild contract
- relevant tests

## Out of scope

- `python/*`
- PR #42 worktree cleanup lane
- redoing PR #41 RegionManager ownership
- speculative redesign / visual refresh / UX invention
- broad docs churn beyond what the new PR actually changes

## Validation requirements

Run and report at least:
- targeted tests for the files you touch
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- browser smoke in the rebuilt UI

Also include in the PR body:
- which parts of `parse-builder-auto` were salvaged vs discarded
- which oracle/live files were used as the reference
- confirmation that PR #41 remained non-overlapping
- exact tests run

## Reporting requirements

Open **one fresh Builder implementation PR** from current `origin/main`.

In the PR body, include:
- what remaining non-RegionManager annotate-shell drift or decision behavior was found
- exactly which local WIP files were reused or intentionally discarded
- exactly which oracle/live files or runtime surfaces you used as the reference
- confirmation that PR #41 remained non-overlapping
- exact tests run

## Academic / fieldwork considerations

- PARSE annotate mode is a fieldwork workstation, not a UI playground.
- Researchers depend on stable annotate shell behavior, predictable control placement, and reproducible decision persistence semantics.
- This follow-up should reduce ambiguity, not create a second competing persistence model.
