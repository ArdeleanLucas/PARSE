# parse-builder next task — compare contract and persistence hardening bundle

## Goal

Ship **one larger frontend-only follow-up PR** that consolidates the remaining compare-side contract and persistence cleanup, while keeping the React UI visually and behaviorally identical to the original PARSE workstation.

## Why this is the right next task now

- Lucas explicitly wants **longer tasks**, because the overhead of writing tiny PR prompts is now worse than just doing the work.
- The current frontend queue is fragmented across several small implementation PRs:
  - PR #27 — BorrowingPanel typed CLEF client cleanup
  - PR #29 — `configStore.update()` wiring
  - PR #31 — CognateControls save-failure hardening
- Instead of creating more tiny slices, the next Builder move should be to consolidate the remaining frontend-only compare cleanup into one coherent implementation PR.
- The hard product rule still applies: **no UI re-imagining**. The original PARSE UI remains the spec.

## Hard UI constraint

- **Do not redesign the UI.**
- Use `/home/lucas/gh/ardeleanlucas/parse` — especially `parse.html`, `compare.html`, `js/annotate/*`, and `js/compare/*` — as the source of truth for layout, labels, control ordering, and interaction flow.
- This task is about frontend contract/persistence correctness and parity-safe hardening, not visual change.

## Current grounded context

### Repo state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch: current `origin/main`
- Current visible `origin/main`: `0d78bb8` (`test(compare): harden compute semantics regressions (#28)`)
- Open frontend implementation PRs at handoff time:
  - PR #27 — `fix(compare): use typed CLEF client in BorrowingPanel`
  - PR #29 — `fix(config): wire configStore update to typed client`
  - PR #31 — `fix(compare): harden CognateControls save failures`
- Backend lane to avoid overlapping with:
  - PR #23 — parse-back-end contract-parity prompt

### Key current-main surfaces
- `src/components/compare/BorrowingPanel.tsx`
- `src/stores/configStore.ts`
- `src/components/compare/CognateControls.tsx`
- corresponding tests under `src/components/compare/*` and store tests

## Specific task

Create **one fresh Builder implementation PR** from current `origin/main` that resolves the remaining compare-side contract/persistence cleanup in a bundled, parity-safe way.

### Required implementation direction
1. **Audit PRs #27, #29, and #31 first.**
   - Determine which changes are still needed on current `origin/main`.
   - Absorb or supersede the safe remaining delta into one new implementation PR rather than continuing a chain of micro-fixes.
   - If one of the PRs is already effectively obsolete, say so explicitly in the new PR body.

2. **Finish the BorrowingPanel contract cleanup.**
   - Ensure `BorrowingPanel` uses the typed CLEF client path only.
   - Remove any remaining ad hoc config-loading drift if still present.
   - Preserve the existing UI appearance and user workflow.

3. **Finish `configStore.update()` parity.**
   - Wire `src/stores/configStore.ts::update()` to the existing typed `updateConfig()` client helper.
   - Remove stale TODO / warning / fake-unimplemented behavior.
   - Add or update regression coverage so store state and API wiring remain truthful.

4. **Finish CognateControls save-path hardening.**
   - Make `src/components/compare/CognateControls.tsx` truthful about save failure behavior.
   - Remove obsolete fallback assumptions.
   - Add explicit regression tests for success and failure semantics.
   - Keep visible UI changes at zero unless a tiny unavoidable error surface is truly necessary.

5. **Keep the UI identical to the original.**
   - No relabeling, no layout drift, no control regrouping, no chrome refresh.
   - If you discover an unavoidable visible deviation, keep it minimal and justify it.

## In scope

- `src/components/compare/BorrowingPanel.tsx`
- `src/stores/configStore.ts`
- `src/components/compare/CognateControls.tsx`
- directly related tests / client/store typings required to finish the bundled cleanup
- parity verification against the original workstation files

## Out of scope

- `python/server.py`
- parse-back-end PR #23
- annotate-mode redesign
- compare-mode redesign
- speculative UX improvements
- opening another chain of tiny frontend PRs when one bundled pass can finish the remaining safe work

## Validation requirements

Run and report at least:
- `npm run test -- --run src/components/compare/CognateControls.test.tsx`
- `npm run test -- --run src/components/compare/BorrowingPanel.test.tsx`
- any relevant `configStore` tests you add/update
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Reporting requirements

Open one fresh implementation PR from current `origin/main`.

In the PR body, include:
- which of PRs #27 / #29 / #31 were absorbed, superseded, or found already obsolete
- the exact remaining frontend delta you finished
- confirmation that the UI stayed aligned with the original / no UI re-imagining
- exact tests run

## Academic / fieldwork considerations

- Comparative review work depends on stable, trustworthy cognate and borrowing controls.
- Silent persistence drift risks corrupting adjudication state and downstream export interpretation.
- UI stability matters for fieldwork speed and reviewer trust; correctness should improve without visual churn.
