# parse-builder next task — shell UI parity audit and correction bundle

## Goal

Ship **one larger frontend-only follow-up PR** that audits the remaining shell/chrome UI in PARSE-rebuild against the oracle/live PARSE interface and corrects visible parity drift without redesigning the workstation.

## Why this is the right next task now

- Lucas explicitly wants **longer tasks**, because writing many tiny prompt PRs now costs more than the implementation slices themselves.
- PR #38 just landed a narrow parity correction by removing rebuild-only compare compute explainer copy.
- The next coherent Builder-sized task is therefore to continue parity work at the **shell/chrome layer**, not another tiny one-off copy tweak.
- Builder already has a separate non-overlapping compare-contract implementation PR in flight:
  - PR #34 — `fix(compare): bundle frontend contract hardening`
- The safest next Builder task is a frontend-only parity bundle that avoids PR #34’s files and focuses on the top-level shell surfaces users see constantly while working.

## Hard UI constraint

- **Do not redesign the UI.**
- **Do not modernize the UI for its own sake.**
- **Do not rename, regroup, or restyle controls unless matching the canonical/oracle UI requires it.**
- Visible changes are allowed only when they correct drift back toward the canonical PARSE interface.

## Source of truth

Use the oracle/live PARSE repo as the canonical UI reference:
- `/home/lucas/gh/ardeleanlucas/parse`

Audit against the current live frontend surfaces there, especially:
- `src/ParseUI.tsx`
- any shared shell behavior visible in the live runtime when you run it locally

If a historical cue is clearer in the archival repo, you may inspect `/home/lucas/gh/ArdeleanLucas/PARSE`, but the **primary** reference should remain the oracle/live repo above.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch for your next implementation PR: current `origin/main`
- Current `origin/main`: `72ae7ef` (`fix(ui): remove rebuild-only compare semantics copy (#38)`)
- Recently landed parity slice:
  - PR #38 — compare compute explainer copy removed
- Open Builder implementation PR to avoid overlapping with:
  - PR #34 — `fix(compare): bundle frontend contract hardening`
- Open parse-back-end lanes to stay out of:
  - PR #39 — `refactor(tags): extract tag and export HTTP handlers`
  - PR #37 — queued CLEF HTTP bundle handoff

### Files to focus on for this bundle
Primary rebuild-shell surfaces:
- `src/ParseUI.tsx`
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/components/parse/ConceptSidebar.test.tsx`
- `src/components/parse/RightPanel.test.tsx`
- `src/ParseUI.test.tsx`

## Specific task

Create **one fresh Builder implementation PR** from current `origin/main` that audits and fixes remaining shell/chrome parity drift.

### Required implementation direction
1. **Audit rebuild shell UI against the oracle/live UI first.**
   - Compare current rebuild shell behavior to `/home/lucas/gh/ardeleanlucas/parse`.
   - Focus on actual user-visible differences, not internal refactors.
   - Produce a concise parity checklist in the PR body.

2. **Inspect the highest-risk shell surfaces.**
   At minimum audit:
   - top banner / mode switch / action cluster
   - left concept sidebar search / sorting / filter chips / counters
   - right controls rail section order / labels / chrome / helper copy
   - any remaining rebuild-only explainer text, placeholder text, or shell-status copy that diverges from the oracle UI
   - collapsed vs expanded shell behavior where the rebuild may have drifted from the oracle experience

3. **Correct real drift only.**
   - Fix layout, labels, ordering, spacing/chrome, and interaction-level shell drift where the rebuild no longer matches the canonical UI closely enough.
   - Do not widen the task into speculative UX improvement.

4. **Stay out of PR #34’s contract files.**
   Unless absolutely necessary, do **not** touch:
   - `src/components/compare/BorrowingPanel.tsx`
   - `src/components/compare/CognateControls.tsx`
   - `src/stores/configStore.ts`
   - files that obviously belong to PR #34’s compare-contract bundle

5. **Document any unavoidable deviation.**
   - If a surface cannot be made identical without disproportionate risk, keep the deviation minimal and justify it explicitly in the PR body.

## In scope

- `src/ParseUI.tsx`
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/RightPanel.tsx`
- shell-focused tests in the corresponding test files
- narrowly adjacent shared UI pieces only if required for shell parity

## Out of scope

- backend files under `python/`
- parse-back-end PRs #39 and #37
- compare contract/persistence files already targeted by PR #34
- speculative redesign / visual refresh / product invention
- changing API contracts to support cosmetic preferences

## Validation requirements

Run and report at least:
- `npm run test -- --run src/components/parse/ConceptSidebar.test.tsx src/components/parse/RightPanel.test.tsx src/ParseUI.test.tsx`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- a browser smoke on the rebuilt UI

Also include in the PR body:
- the oracle/live reference files inspected
- a concise checklist of drift found vs corrected
- confirmation that no UI re-imagining was introduced
- any unavoidable remaining deviation

## Reporting requirements

Open **one fresh Builder implementation PR** from current `origin/main`.

In the PR body, include:
- what visible shell drift was found
- exactly which oracle/live files or runtime surfaces you used as the reference
- confirmation that PR #34 remained non-overlapping
- exact tests run

## Academic / fieldwork considerations

- PARSE is a workstation used for sustained linguistic review, not a consumer product demo.
- Fieldwork efficiency depends on stable shell behavior, familiar control placement, and low cognitive overhead while annotating and comparing forms.
- A shell-focused parity pass reduces retraining cost and keeps expert workflows reproducible across sessions and operators.
