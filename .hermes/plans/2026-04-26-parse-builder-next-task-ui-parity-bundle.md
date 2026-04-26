# parse-builder next task — UI parity audit and correction bundle

## Goal

Ship **one larger frontend-only follow-up PR** that audits the React workstation against the oracle/live PARSE UI and corrects any visible, structural, or interaction drift, while keeping the rebuild UI identical in practice to the canonical PARSE interface.

## Why this is the right next task now

- Lucas explicitly wants **longer tasks**, because prompt-writing overhead is now worse than the tiny implementation slices.
- The current Builder implementation PR (#34) is a bundled compare contract/persistence cleanup. The next coherent Builder-sized task should move up one level from contract correctness to **UI parity**.
- Lucas set a hard product rule: **no UI re-imagining**. The rebuild UI should match the canonical/oracle PARSE UI, not reinterpret it.
- A dedicated parity bundle is the right next task because it is:
  - substantial enough to justify a real Builder pass
  - fully frontend-owned
  - independent of parse-back-end PR #35
  - directly aligned with Lucas’s strongest product constraint

## Hard UI constraint

- **Do not redesign the UI.**
- **Do not modernize for its own sake.**
- **Do not rename, regroup, or restyle controls unless matching the canonical UI requires it.**
- Visible changes are allowed only when they correct drift back toward the canonical/oracle PARSE interface.

## Source of truth

Use the oracle/live PARSE repo as the canonical UI reference:
- `/home/lucas/gh/ardeleanlucas/parse`

Audit against the current live frontend surfaces there, especially:
- `src/ParseUI.tsx`
- `src/components/annotate/*`
- `src/components/compare/*`
- relevant shared UI components / shell chrome

If you discover a needed historical cue that is clearer in the archival repo, you may inspect `/home/lucas/gh/ArdeleanLucas/PARSE`, but the **primary** reference for parity should be the live/oracle repo above.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch for your next implementation PR: current `origin/main`
- Current `origin/main`: `70f9783` (`refactor(config): extract config and CSV import HTTP handlers (#33)`)
- Active Builder implementation PR to finish first:
  - PR #34 — `fix(compare): bundle frontend contract hardening`
- Non-overlap backend lane:
  - PR #35 — `docs: add parse-back-end tags/export bundle handoff`

### Why this follows PR #34 cleanly
- PR #34 is about compare-side contract/persistence correctness.
- This next task is about **layout / label / control / interaction parity** across the React workstation.
- That separation keeps the queue understandable:
  - PR #34 = contract correctness
  - next PR = UI parity bundle

## Specific task

Create **one fresh Builder implementation PR** from current `origin/main` after PR #34 that audits and fixes React UI parity drift.

### Required implementation direction
1. **Audit the rebuild UI against the oracle/live UI first.**
   - Compare current rebuild sources to `/home/lucas/gh/ardeleanlucas/parse`.
   - Focus on actual user-visible differences, not internal refactors.
   - Produce a concise parity checklist in the PR body.

2. **Inspect the highest-risk parity surfaces.**
   At minimum audit:
   - top-level shell structure / mode switching
   - annotate-mode panel arrangement
   - compare-mode panel arrangement
   - waveform / transcript / annotation control grouping where applicable
   - compare concept table / side-panel structure
   - lexeme detail / tags / comments / borrowing-related panel labels and affordances
   - chat / side drawers / modals that visibly changed shell behavior

3. **Correct real drift only.**
   - Fix layout, labels, control ordering, spacing/chrome, and interaction-level drift where the rebuild no longer matches the canonical UI closely enough.
   - Do not widen the task into speculative UX improvement.

4. **Keep behavior-preserving refactors separate from visible parity fixes.**
   - If you need a small refactor to make a parity fix safe, keep it narrow and explain it.
   - The visible goal is parity, not architectural cleanup.

5. **Document any unavoidable deviation.**
   - If a surface cannot be made identical without disproportionate risk, keep the deviation minimal and justify it explicitly in the PR body.

## In scope

- `src/ParseUI.tsx`
- `src/components/annotate/*`
- `src/components/compare/*`
- relevant shared UI components under `src/components/shared/*`
- parity-focused tests / browser verification notes

## Out of scope

- backend files under `python/`
- parse-back-end PR #35
- expanding PR #34 instead of opening a clean follow-up PR
- speculative redesign / visual refresh / product invention
- changing API contracts to support a cosmetic preference

## Validation requirements

Run and report at least:
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- a browser smoke on the rebuilt UI

Also include in the PR body:
- the parity reference files inspected in `/home/lucas/gh/ardeleanlucas/parse`
- a concise checklist of drift found vs corrected
- confirmation that no UI re-imagining was introduced
- any unavoidable remaining deviation

## Reporting requirements

Open **one fresh Builder implementation PR** from current `origin/main` after PR #34.

In the PR body, include:
- what visible drift was found
- exactly which canonical/oracle files you used as the reference
- whether any part of PR #34 had to be accounted for when doing the parity pass
- exact tests run

## Academic / fieldwork considerations

- PARSE is a workstation used for sustained linguistic review, not a consumer UI playground.
- Fieldwork efficiency depends on stable control placement, predictable panel flow, and familiar interaction patterns.
- A parity-focused correction pass reduces user retraining cost and keeps comparative/annotation work reproducible across sessions and operators.
