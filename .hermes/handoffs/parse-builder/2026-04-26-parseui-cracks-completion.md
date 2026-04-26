---
agent: parse-builder
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #61, #62, #63, #69 should land first (or at least be uncontested) so this branches from a clean origin/main
related_skills:
  - parse-react-shell-refactor-planning
  - parse-react-shell-refactor-execution
  - parse-vitest-hoisted-store-mocks
  - test-driven-development
---

# parse-builder follow-on — complete ParseUI.tsx structural cracks (close the ≤1800 LoC gap)

**Why this exists:** PR #69 (`refactor(parseui): extract AnnotateView from ParseUI.tsx`) shipped the named `AnnotateView` component cleanly (685 LoC, paired test, screenshot) but **did not hit the original "done" criterion of `wc -l src/ParseUI.tsx ≤ 1800`**. After all four extraction PRs (#61, #62, #63, #69) merge, ParseUI.tsx will still be ~3793 LoC. The PR body honestly acknowledged the gap. This handoff closes it.

The remaining 2000+ LoC fall into two clear groups, neither of which is part of any named React component — they're helper sub-components and parsing utilities that should never have lived in `ParseUI.tsx` in the first place.

## Working environment

Same guardrails as PR #58. Verify before opening any PR:

```
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)   # CORRECT — NOT ArdeleanLucas/PARSE
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...   # --repo flag mandatory
```

If `git remote -v` shows `ArdeleanLucas/PARSE`, you are in the oracle clone — switch to the rebuild clone before continuing. Three prior refactor PRs (#225, #226, #229) had to be reverted because they landed on the wrong remote.

## Scope

### In scope (one PR per group; can be parallel branches off origin/main)

**Group A — Annotate helpers** (still inline in ParseUI.tsx after PR #69):

- `JobLogsModal` (lines ~3568+, ~110 LoC) → `src/components/annotate/JobLogsModal.tsx` + `.test.tsx`
- `LexemeSearchBlock` (lines ~3680+, ~70 LoC) → `src/components/annotate/LexemeSearchBlock.tsx` + `.test.tsx`
- `TranscriptionLanesControls` (lines ~3752+, remainder) → `src/components/annotate/TranscriptionLanesControls.tsx` + `.test.tsx`

These are referenced from `ParseUI`'s render at lines ~3464–3553 — the components are passed as render props (`annotateSpeakerTools`, `annotateAuxTools`) and via direct JSX (`<JobLogsModal ...>`). Either keep them imported in ParseUI.tsx and passed through unchanged, or move the prop construction inside `AnnotateView.tsx` and have ParseUI just hand it `selectedSpeakers[0]`. The latter is structurally cleaner; pick one and explain in the PR body.

**Group B — Reference-form parsing utilities** (top-of-file, lines ~299–518):

These have no dependency on React or ParseUI's local closures:
- `NON_LATIN_SCRIPT_RE`, `LATIN_SCRIPT_HINTS`, `RTL_CODES`, `CARD_TONES` — constants
- `classifyRawFormString`, `_parseOneEntry`, `referenceCardStyle` — internal helpers
- `parseReferenceFormList`, `resolveReferenceFormLists`, `resolveFormSelection`, `ReferenceFormEntry` (type) — already-public re-exports

Target: `src/lib/referenceFormParsing.ts`. Keep `ParseUI.tsx` re-exporting the four public symbols (`pickOrthoIntervalForConcept`, `parseReferenceFormList`, `resolveReferenceFormLists`, `resolveFormSelection`, `ReferenceFormEntry`) for backward compatibility — the original PR #58 prompt's "Out of scope" section is explicit that those re-exports stay until a separate cleanup task removes them. Do not change call sites elsewhere in this PR.

Tests: `src/lib/referenceFormParsing.test.ts` covering the existing scenarios in `src/__tests__/referenceFormLists.test.ts` (or just move that test file to `src/lib/referenceFormParsing.test.ts` and update its imports).

### Out of scope

- Touching `AnnotateView.tsx`, `ManageTagsView.tsx`, `AIChat.tsx` — extracted, leave alone
- Renaming or removing the four public re-exports from ParseUI.tsx
- Any behavior change, prop signature change, or store mutation
- Touching `python/`
- Worktree, branch, or PR cleanup of older parse-builder work

## Sequence

**Two PRs, branched independently off `origin/main`. They can be opened in parallel:**

### PR A — Extract the three Annotate helpers

Branch: `feat/parseui-extract-annotate-helpers`

Procedure:
1. Re-derive line numbers from current ParseUI.tsx; trust grep, not the line numbers in this prompt:
   ```
   $ grep -n 'function JobLogsModal\|function LexemeSearchBlock\|function TranscriptionLanesControls' src/ParseUI.tsx
   ```
2. Cut each helper into its own sibling file under `src/components/annotate/`. Keep the function name the same; do not rename.
3. Decide on the prop-passing pattern (keep import in ParseUI.tsx vs move into AnnotateView.tsx) and apply consistently. Document the choice in PR body.
4. Add paired test files. Each test file covers at minimum:
   - `JobLogsModal.test.tsx` — open/close, jobId render, error state, log-list render
   - `LexemeSearchBlock.test.tsx` — submit search, render results, empty state
   - `TranscriptionLanesControls.test.tsx` — control visibility toggle, lane-kind selection
5. Run gates: `npm run typecheck`, `npm run test`, `npm run build`, `ParseUI.test.tsx` still green.
6. Browser regression: open Annotate, open JobLogs (any job), do a lexeme search, toggle a lane control. **Screenshot in PR body.**

Acceptance: ParseUI.tsx down ~250–300 LoC. Three new files ≤200 LoC each. Test files ≥60 LoC each, green.

### PR B — Lift reference-form parsing into src/lib/

Branch: `feat/parseui-lift-reference-form-parsing`

Procedure:
1. Cut the lines ~299–518 block (constants + helpers + public functions) into `src/lib/referenceFormParsing.ts`. Verbatim move; only diff is added `export` keywords on the previously-private helpers if the test file needs them.
2. In `src/ParseUI.tsx`, replace the cut section with a re-export:
   ```ts
   export {
     parseReferenceFormList,
     resolveReferenceFormLists,
     resolveFormSelection,
     type ReferenceFormEntry,
   } from './lib/referenceFormParsing';
   ```
   `pickOrthoIntervalForConcept` stays in ParseUI.tsx — it's already separate and depends on `Concept` types defined locally.
3. Move `src/__tests__/referenceFormLists.test.ts` to `src/lib/referenceFormParsing.test.ts` and update its imports. Or add a new test file at the new location and delete the old one. Either way, no test coverage loss.
4. Run gates as PR A.
5. No browser regression needed — these are pure functions. Verify by checking that Compare mode still renders RTL/script-hint badges correctly (open Compare, eyeball that things look right, mention in PR body — no screenshot required for pure-function refactor).

Acceptance: ParseUI.tsx down ~220 LoC. New `src/lib/referenceFormParsing.ts` ≤230 LoC. Test file relocated/intact, green.

## Cumulative target after both PRs land

- `wc -l src/ParseUI.tsx` ≤ **1800** (the original PR #58 target)
- `src/components/annotate/`: AnnotateView, JobLogsModal, LexemeSearchBlock, TranscriptionLanesControls — all with paired tests
- `src/lib/referenceFormParsing.ts` exists with paired test
- All existing ParseUI re-exports still importable for backward compat
- No behavior change, no contract change

## Test gates (every PR)

- `npm run typecheck` — green
- `npm run test` — green, no skipped tests added
- `npm run build` — green
- `ParseUI.test.tsx` and any test that imports `parseReferenceFormList` etc. via ParseUI.tsx still pass without modification
- Browser screenshot in PR A (Annotate workstation showing the three helpers in their primary states); none needed for PR B

## Conventions

- One commit per logical operation
- PR title format: `refactor(parseui): <action>`
- Co-author line: `Co-Authored-By: parse-builder <noreply@anthropic.com>`
- Do not merge your own PRs
- Do not touch `AnnotateView.tsx`, `ManageTagsView.tsx`, `AIChat.tsx`

## Out-of-band notes

- Always branch from `git fetch origin main --quiet && git rev-parse origin/main`, never local HEAD.
- If you spot any of the cut helpers being used by Compare or Tags surfaces (not just Annotate), flag in PR body — they may belong in `src/components/shared/` instead. Quick `grep -rn JobLogsModal src/` before cutting will tell you.
- After both PRs land, the next parse-builder task (TBD by coordinator) is likely **TranscriptionLanes.tsx** decomposition (943 LoC, next-largest annotate monolith) following the same per-component pattern. Do not start that work in this handoff.
