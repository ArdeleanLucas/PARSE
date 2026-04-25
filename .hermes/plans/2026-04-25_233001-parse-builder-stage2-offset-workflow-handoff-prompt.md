# ParseBuilder next task — Stage 2 offset workflow extraction

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Date:** 2026-04-25
**Owner:** parse-builder
**Status:** queued / ready on current `origin/main`

## Goal

Continue the merged ParseUI shell refactor by extracting the **offset workflow** out of `src/ParseUI.tsx` into a dedicated hook + modal layer, while preserving all current timestamp-offset behavior and keeping the shell/controller thinner.

## Why this is the right next task

- Rebuild `main` now already contains the completed earlier slices:
  - PR #1 — rebuild repo context
  - PR #3 — ParseUI Stage 0 + Stage 1 shell baseline and islands
  - PR #4 — backend HTTP helper extraction
  - PR #8 — external API HTTP handler extraction
- The old stage branches are merged/deleted. This continuation should start from **fresh `origin/main`**, not from the old stage-0/stage-1 branches.
- `src/ParseUI.tsx` is still large (**4932 lines**, verified on current rebuild `main`).
- The two safest shell islands already extracted are in place:
  - `src/components/parse/ConceptSidebar.tsx`
  - `src/components/parse/RightPanel.tsx`
- The next biggest coherent shell-specific seam is the **offset state machine + modal** that still lives inline in `ParseUI.tsx`.

## Current grounded context

Verified on current rebuild `origin/main` before writing this prompt:

- Current `origin/main` tip: `f812798 refactor: extract external API HTTP handlers (#8)`
- Recent rebuild `main` history:
  - `f812798` — PR #8
  - `f4fa47d` — PR #4
  - `7d17272` — PR #3
  - `d1bc2b6` — PR #1
- Fresh validation baseline in a clean worktree from `origin/main`:
  - `npm run test -- --run` → **43 files passed / 292 tests passed**
  - `./node_modules/.bin/tsc --noEmit` → **clean**
- Current shell extraction status:
  - `ConceptSidebar.tsx` + `ConceptSidebar.test.tsx` exist
  - `RightPanel.tsx` + `RightPanel.test.tsx` exist
  - `CompareView` does **not** exist yet
  - `useOffsetState` does **not** exist yet
  - `OffsetAdjustmentModal` does **not** exist yet
- Inline shell components still inside `src/ParseUI.tsx`:
  - `AIChat` — around line `705`
  - `ManageTagsView` — around line `1316`
  - `AnnotateView` — around line `1543`
- Offset workflow hotspots still inline in `src/ParseUI.tsx`:
  - offset state machine begins around **`2653`**
  - manual anchors + capture toast live around **`2680-2827`**
  - detect/apply/manual-submit handlers live around **`2829-2922`**
  - topbar offset status chip lives around **`3322-3356`**
  - offset modal root begins around **`4334`**
  - manual-mode modal body begins around **`4377`**
  - manual capture button is around **`4466`**
  - apply/error controls extend through roughly **`4653`**
- Existing shell-level offset tests already in `src/ParseUI.test.tsx`:
  - annotate anchor capture / manual-adjusted flag
  - manual offset modal capture + consensus
  - topbar status chip + detecting modal while polling

## The specific task

Extract the current inline offset workflow into:

```text
src/hooks/useOffsetState.ts
src/components/parse/modals/OffsetAdjustmentModal.tsx
```

with any **small, justified helper/type file** only if it materially reduces prop churn.

### Preferred target shape

- `useOffsetState.ts`
  - owns the offset state machine
  - owns manual anchors
  - owns manual consensus derivation
  - owns detect/apply/manual-submit flows
  - owns crash-log open state and any fetch/poll callbacks needed for the offset workflow
  - owns capture-toast lifecycle if that keeps the shell thinner
- `OffsetAdjustmentModal.tsx`
  - renders the detecting/manual/detected/applied/error UI
  - receives explicit typed props
  - does **not** own API effects directly
- `ParseUI.tsx`
  - becomes the orchestrator/wiring point only
  - keeps shell-level mode/layout wiring
  - should stop owning the full offset workflow state machine inline

## Scope boundary

### In scope
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/hooks/useOffsetState.ts` *(new)*
- `src/hooks/__tests__/useOffsetState.test.ts` *(new, strongly preferred)*
- `src/components/parse/modals/OffsetAdjustmentModal.tsx` *(new)*
- `src/components/parse/modals/OffsetAdjustmentModal.test.tsx` *(new, strongly preferred)*

### Allowed only if truly necessary
- a tiny shared type/helper file under `src/components/parse/` or `src/hooks/`
- minimal prop-type updates in already-extracted shell components if the offset wiring genuinely requires them

### Read-only for this task
- `python/**`
- `src/api/client.ts`
- `src/api/types.ts`
- `src/stores/**`
- `src/components/annotate/**`
- `src/components/compare/**`
- `src/components/shared/**`
- `src/components/compute/**`
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/RightPanel.tsx`

If a bug is discovered in a read-only dependency, note it in the PR rather than broadening scope.

## Behavior that must not regress

This slice is successful only if **all** of the following still work exactly:

1. **Annotate anchor capture**
   - clicking `annotate-capture-anchor`
   - marks the lexeme as manually adjusted
   - shows the temporary capture toast
2. **Manual offset modal**
   - opens from the drawer
   - captures anchors from current selection
   - shows live consensus
   - allows anchor removal
3. **Auto-detect flow**
   - opens the detecting modal
   - updates the topbar offset chip from polling progress
   - preserves progress message behavior
4. **Apply flow**
   - keeps protected/manual lexeme counts intact
   - preserves reload/apply success behavior
5. **Error flow**
   - preserves offset error messaging
   - preserves “View crash log” reachability
6. **Shell contract**
   - topbar offset chip stays wired
   - `RightPanel` timestamp tools still trigger the same shell behavior
   - `AnnotateView` capture hook still works without behavioral drift

## TDD execution order

### 1. Start from fresh `origin/main`
Use a fresh branch/worktree, not any deleted stage branch.

Recommended bootstrap:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --prune
git switch -c refactor/parseui-stage2-offset-workflow origin/main
```

### 2. Freeze the baseline
If needed in a fresh worktree:

```bash
ln -s /home/lucas/gh/ardeleanlucas/parse/node_modules node_modules
npm run test -- --run
./node_modules/.bin/tsc --noEmit
rm node_modules
```

### 3. Add failing tests first
Before extracting code, add or strengthen tests for the slice.

#### Minimum required test coverage
- shell test: annotate anchor capture still marks lexeme + shows toast
- shell test: manual offset modal still captures anchors + shows consensus
- shell test: auto-detect still updates topbar chip + modal progress text
- direct test(s): `useOffsetState` transitions and helper behaviors
- direct test(s): `OffsetAdjustmentModal` renders the correct phase UI from props

If some existing shell tests already cover part of the flow, keep them and add the **new direct tests** rather than deleting shell coverage.

### 4. Extract the hook first
Move the offset state machine out of `ParseUI.tsx` before moving the modal UI.

Suggested responsibilities for `useOffsetState`:
- `offsetState`
- `manualAnchors`
- `manualBusy`
- `protectedLexemeCount`-related derivation inputs/outputs as appropriate
- `captureToast` lifecycle if it meaningfully belongs in the hook
- `captureCurrentAnchor()`
- `captureAnchorFromBar()`
- `removeManualAnchor()`
- `detectOffsetForSpeaker()`
- `applyDetectedOffset()`
- `submitManualOffset()`
- crash-log open/close state if that makes the modal/shell split cleaner

### 5. Extract the modal second
Create `OffsetAdjustmentModal.tsx` as a presentational/controller component with explicit typed props.

Rules:
- no hidden store reach-through if props are reasonable
- no broad prop dumping from `ParseUI` if a cleaner typed boundary is possible
- keep the current modal body semantics and test IDs stable where feasible

### 6. Shrink `ParseUI.tsx`
After hook + modal extraction, `ParseUI.tsx` should only:
- invoke the hook
- pass typed data/callbacks to the modal
- wire topbar + right-panel triggers
- wire annotate capture callback into `AnnotateView`

Do **not** also try to extract `CompareView`, `AIChat`, or `ManageTagsView` in this same PR unless the offset extraction unexpectedly becomes trivial and the additional move is truly no-risk. The safe default is **one coherent slice**.

## Validation gates

### Required after implementation
```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

### Required targeted checks
```bash
npm run test -- --run src/ParseUI.test.tsx
npm run test -- --run src/components/parse/modals/OffsetAdjustmentModal.test.tsx
npm run test -- --run src/hooks/__tests__/useOffsetState.test.ts
```

If the test placement differs, run the equivalent targeted suite(s) and name them in the PR body.

## Files likely to change

### Expected edits
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/hooks/useOffsetState.ts` *(new)*
- `src/hooks/__tests__/useOffsetState.test.ts` *(new)*
- `src/components/parse/modals/OffsetAdjustmentModal.tsx` *(new)*
- `src/components/parse/modals/OffsetAdjustmentModal.test.tsx` *(new)*

### Files that should not change in this task
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/api/client.ts`
- `src/api/types.ts`
- `python/**`

## Branch / PR guidance

Recommended branch:

```text
refactor/parseui-stage2-offset-workflow
```

Recommended PR description themes:
- this is the **next shell continuation after merged PR #3**
- offset workflow extracted into hook + modal seam
- behavior-preserving shell refactor only
- no backend/API/store contract changes

## Final note

This task should keep parse-builder squarely in the frontend shell lane: one coherent, test-backed, behavior-preserving extraction that removes the most complicated remaining state machine from `ParseUI.tsx` without reopening the already-merged stage-1 island work or drifting into backend changes.
