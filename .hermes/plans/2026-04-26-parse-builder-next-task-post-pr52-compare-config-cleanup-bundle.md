# parse-builder next task — post-PR52 compare/config cleanup bundle

## Goal

Ship **one fresh frontend-only Builder implementation PR** from the latest `origin/main` that bundles the next real compare-side cleanup slice after the currently open frontend implementation pair (**PR #50** compute-contract semantics and **PR #52** Actions-menu normalization).

The task is to reconcile three still-open frontend contract/reliability gaps without redesigning the UI:

1. remove the remaining bare CLEF contact-language fetch from `BorrowingPanel`
2. make `configStore.update()` use the real typed client + server route
3. stop `CognateControls` from silently pretending saves succeeded when enrichment persistence fails

This is a **batched cleanup bundle**, not three more micro-prompts.

## Why this is the right next task now

- Current `origin/main` still contains the exact three gaps above.
- They are all **frontend-owned**, **narrow**, and **non-overlapping** with the currently open Builder implementation PRs:
  - **PR #50** `fix(compare): harden compute contract semantics`
  - **PR #52** `refactor(actions): normalize export and tag import handlers`
- Lucas prefers **larger coherent follow-up bundles** over more tiny task PRs when the work can be grouped cleanly.
- There are already closed/stale micro-PR branches for each sub-slice (`#27`, `#29`, `#31`), which means the best next move is to **absorb/supersede their still-valid work into one clean successor implementation PR** grounded on current `origin/main`.

## Current grounded evidence

### 1. `BorrowingPanel` still bypasses the typed client

On current `origin/main`:
- `src/components/compare/BorrowingPanel.tsx:123-147` still does a direct
  `fetch("/config/sil_contact_languages.json")`
- The repo already has the typed client surface `getClefConfig()` in `src/api/client.ts`
- The backend already exposes `GET /api/clef/config` in `python/server.py`

This is the remaining visible no-bare-fetch violation in a compare UI component.

Relevant salvage input already exists but is unmerged:
- closed PR **#27** / branch `feat/borrowing-panel-typed-client`
- current diff vs `origin/main` still touches only:
  - `src/components/compare/BorrowingPanel.tsx`
  - `src/components/compare/BorrowingPanel.test.tsx`

### 2. `configStore.update()` is still a stub even though the server route exists

On current `origin/main`:
- `src/stores/configStore.ts:32-35` still says:
  - `// TODO: implement PATCH /api/config when backend supports it`
  - `console.warn("[configStore] update() is not yet implemented")`
- But the active contract already includes:
  - `updateConfig()` in `src/api/client.ts`
  - `PUT /api/config` in `python/server.py`
  - `AGENTS.md` contract table marking that route as implemented

So the store contract is behind the live client/server surface.

Relevant salvage input already exists but is unmerged:
- closed PR **#29** / branch `feat/configstore-update`
- current diff vs `origin/main` still touches only:
  - `src/stores/configStore.ts`
  - `src/stores/configStore.test.ts`

### 3. `CognateControls` still swallows save failures and leaves misleading UI state

On current `origin/main`:
- `src/components/compare/CognateControls.tsx:161-173` catches `save()` failures and ignores them
- the component still updates local grouped state optimistically and still triggers downstream change handling
- that means the UI can imply a cognate re-grouping succeeded even when persistence failed

That is bad for adjudication reproducibility.

Relevant salvage input already exists but is unmerged:
- closed PR **#31** / branch `feat/cognate-controls-save-hardening`
- current diff vs `origin/main` still touches only:
  - `src/components/compare/CognateControls.tsx`
  - `src/components/compare/CognateControls.test.tsx`

## Source of truth

Primary sources for the implementation:
- `src/components/compare/BorrowingPanel.tsx`
- `src/components/compare/BorrowingPanel.test.tsx`
- `src/stores/configStore.ts`
- `src/components/compare/CognateControls.tsx`
- `src/components/compare/CognateControls.test.tsx`
- `src/api/client.ts`
- `python/server.py`
- `AGENTS.md`

Salvage inputs to inspect, but **not** to trust blindly:
- branch `feat/borrowing-panel-typed-client` / closed PR #27
- branch `feat/configstore-update` / closed PR #29
- branch `feat/cognate-controls-save-hardening` / closed PR #31

Use those only as candidate diffs to fold forward onto current `origin/main`.

## Specific task

Create **one fresh Builder implementation PR** from the latest `origin/main` that bundles these three compare/config cleanup items.

### Required implementation direction

1. **BorrowingPanel → typed CLEF client**
   - replace the direct fetch path with the canonical typed-client route
   - prefer `getClefConfig()` / current CLEF metadata instead of reading `/config/sil_contact_languages.json` directly from the component
   - preserve the same visible adjudication UI and fallback behavior

2. **configStore.update() → real persistence path**
   - wire `configStore.update()` through `updateConfig()`
   - merge successful patches back into local store state
   - surface failures via the store error state instead of a console-only stub
   - add a focused store test file if needed

3. **CognateControls save-failure hardening**
   - make save operations truthfully reflect persistence outcomes
   - do not silently keep or report a regrouping as successful when `enrichmentStore.save()` fails
   - revert or otherwise clearly isolate optimistic local changes on failure
   - keep user-facing behavior stable when saves succeed

4. **Bundle, don’t scatter**
   - this should land as one coherent follow-up PR, not three separate PRs
   - if the closed micro-PR diffs are still correct, absorb/supersede them in the new branch
   - if they have drifted, re-implement the same intent cleanly on current main

5. **Keep the UI visually identical**
   - no redesign
   - no new compare affordances
   - no copy churn unless required for truthful error handling

## In scope

- `src/components/compare/BorrowingPanel.tsx`
- `src/components/compare/BorrowingPanel.test.tsx`
- `src/stores/configStore.ts`
- `src/stores/configStore.test.ts` (new if needed)
- `src/components/compare/CognateControls.tsx`
- `src/components/compare/CognateControls.test.tsx`
- tiny shared helper/test additions only if clearly justified

## Out of scope

- PR #50 compute-contract implementation work
- PR #52 Actions-menu implementation work
- backend route changes
- annotate-mode parity work
- broad `ParseUI.tsx` refactors
- UI redesign / shell layout changes

## Validation requirements

Run and report at least:
- targeted tests for all touched surfaces
  - `BorrowingPanel.test.tsx`
  - `configStore.test.ts` if added
  - `CognateControls.test.tsx`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- browser smoke if any compare-side visible behavior changes

## Reporting requirements

Open **one fresh Builder implementation PR** from current `origin/main`.

In the PR body include:
- confirmation that this bundle supersedes the old micro-slices from closed PRs `#27`, `#29`, and `#31`
- what changed in each of the three cleanup areas
- confirmation of non-overlap with open PRs `#50` and `#52`
- exact tests run
- confirmation that the visible UI remained aligned with the current workstation

## Academic / fieldwork considerations

- Borrowing adjudication is a research judgment workflow; fetching contact-language metadata through the canonical typed contract reduces silent environment drift.
- Config edits must be real writes, not placeholder stubs, or reproducibility of fieldwork setup degrades.
- Cognate regrouping must never silently appear saved when it was not; false persistence is especially harmful in comparative historical review.
