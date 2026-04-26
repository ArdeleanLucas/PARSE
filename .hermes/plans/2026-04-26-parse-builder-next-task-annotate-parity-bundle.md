# parse-builder next task — annotate workstation parity bundle

## Goal

Ship **one larger frontend-only follow-up PR** that audits the remaining annotate-mode workstation UI in PARSE-rebuild against the oracle/live PARSE interface and corrects visible parity drift without redesigning the workstation.

## Why this is the right next task now

- Lucas explicitly wants **longer tasks**, because prompt-writing overhead is now worse than the implementation slices themselves.
- PR #38 already landed the most obvious compare-controls shell drift by removing rebuild-only explanatory copy.
- That means the next meaningful Builder-sized task should be a **different parity surface**, not a stale re-send of the same shell-copy work.
- The most coherent next frontend-only bundle is annotate-mode parity:
  - transcript / annotation / suggestions / chat panel arrangement
  - annotate control labels and affordances
  - waveform/region management chrome where the rebuild may drift from the oracle UI
- This is substantial enough for one real Builder pass and stays non-overlapping with the open compare-contract and backend lanes.

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
- `src/components/annotate/*`
- relevant shared components used by annotate mode

If a historical cue is clearer in the archival repo, you may inspect `/home/lucas/gh/ArdeleanLucas/PARSE`, but the **primary** reference should remain the oracle/live repo above.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch for your next implementation PR: current `origin/main`
- Current `origin/main`: `bd226e1` (`refactor(tags): extract tag and export HTTP handlers (#39)`)
- Recently landed parity slice:
  - PR #38 — compare compute explainer copy removed
- Open non-overlap lanes:
  - PR #34 — `fix(compare): bundle frontend contract hardening`
  - PR #37 — queued parse-back-end CLEF HTTP bundle

### Files to focus on for this bundle
Primary rebuild annotate surfaces:
- `src/ParseUI.tsx` (annotate-mode sections only)
- `src/components/annotate/AnnotateMode.tsx`
- `src/components/annotate/AnnotationPanel.tsx`
- `src/components/annotate/TranscriptPanel.tsx`
- `src/components/annotate/SuggestionsPanel.tsx`
- `src/components/annotate/ChatPanel.tsx`
- `src/components/annotate/RegionManager.tsx`
- `src/components/annotate/TranscriptionLanes.tsx`
- corresponding annotate tests

## Specific task

Create **one fresh Builder implementation PR** from current `origin/main` that audits and fixes remaining annotate-mode parity drift.

### Required implementation direction
1. **Audit annotate UI against the oracle/live UI first.**
   - Compare current rebuild annotate behavior to `/home/lucas/gh/ardeleanlucas/parse`.
   - Focus on actual user-visible differences, not internal refactors.
   - Produce a concise parity checklist in the PR body.

2. **Inspect the highest-risk annotate surfaces.**
   At minimum audit:
   - panel arrangement/order inside annotate mode
   - waveform / region-management control placement and labels
   - transcript / annotation / suggestions / chat section headings and affordances
   - annotate-mode helper copy, placeholders, button labels, and empty states
   - any rebuild-only status/explainer copy that diverges from the oracle UI

3. **Correct real drift only.**
   - Fix layout, labels, ordering, spacing/chrome, and interaction-level annotate drift where the rebuild no longer matches the canonical UI closely enough.
   - Do not widen the task into speculative UX improvement.

4. **Stay out of compare-contract and backend lanes.**
   Unless absolutely necessary, do **not** touch:
   - files clearly owned by PR #34’s compare-contract bundle
   - backend files under `python/`
   - parse-back-end PR #37 surfaces

5. **Document any unavoidable deviation.**
   - If a surface cannot be made identical without disproportionate risk, keep the deviation minimal and justify it explicitly in the PR body.

## In scope

- annotate-mode UI files under `src/components/annotate/*`
- annotate-mode sections of `src/ParseUI.tsx`
- annotate-focused tests
- narrowly adjacent shared UI pieces only if required for parity

## Out of scope

- backend files under `python/`
- parse-back-end PR #37
- compare-contract/persistence files already targeted by PR #34
- speculative redesign / visual refresh / product invention
- changing API contracts to support cosmetic preferences

## Validation requirements

Run and report at least:
- targeted annotate tests you update
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- a browser smoke on annotate mode in the rebuilt UI

Also include in the PR body:
- the oracle/live reference files inspected
- a concise checklist of drift found vs corrected
- confirmation that no UI re-imagining was introduced
- any unavoidable remaining deviation

## Reporting requirements

Open **one fresh Builder implementation PR** from current `origin/main`.

In the PR body, include:
- what visible annotate-mode drift was found
- exactly which oracle/live files or runtime surfaces you used as the reference
- confirmation that PR #34 remained non-overlapping
- exact tests run

## Academic / fieldwork considerations

- PARSE annotate mode is a fieldwork workstation, not a UI playground.
- Researchers depend on stable annotate panel order, predictable controls, and familiar affordances while segmenting and validating speech data.
- An annotate-focused parity pass reduces retraining cost and keeps annotation workflows reproducible across sessions and operators.
