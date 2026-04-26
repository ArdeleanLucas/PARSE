---
agent: parse-builder
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - none — can run in parallel with #69 / #71 / #73 merge wave (different region of ParseUI.tsx)
related_skills:
  - parse-react-shell-refactor-planning
  - parse-react-shell-refactor-execution
  - parse-vitest-hoisted-store-mocks
  - test-driven-development
---

# parse-builder follow-on — extract Compare-mode helpers from ParseUI.tsx

**Why this exists:** PR #71 + #73 cleared the chase items from PR #70. Math after they + #69 land:

```
current main:       3537 LoC
− #69 (AnnotateView):  583
− #71 (ref-form lift): 230
− #73 (helpers):       227
predicted final:   ~2497 LoC
```

Still ~700 LoC short of the original PR #58 target (`≤1800`). This handoff covers the next ~115 LoC reduction by lifting four small Compare-mode helpers that are orthogonal to the open PRs.

## Working environment

```
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...   # --repo mandatory
```

See [PR #74](https://github.com/TarahAssistant/PARSE-rebuild/pull/74) (AGENTS.md repo-target rule) for the full guard.

## Scope

### In scope (one PR — these helpers are small and tightly related)

Four helpers currently inline in `src/ParseUI.tsx` around lines 531–681 (re-derive line numbers via grep; the wave is shifting them):

| Helper | Approx. LoC | Target file |
|---|---:|---|
| `SimBar` | ~22 | `src/components/compare/CognateCell.tsx` (co-located) |
| `COGNATE_COLORS` constant + `CognateCell` | ~62 | `src/components/compare/CognateCell.tsx` |
| `Pill` | ~9 | `src/components/shared/UIPrimitives.tsx` |
| `SectionCard` | ~22 | `src/components/shared/UIPrimitives.tsx` |

Rationale for the file split:

- `SimBar` + `COGNATE_COLORS` + `CognateCell` are tightly coupled (CognateCell renders SimBar; both visualize cognate similarity). Co-locate in one file.
- `Pill` and `SectionCard` are pure render primitives reused across compare panels (and possibly elsewhere — verify with grep). They belong in a shared primitives file.

### Out of scope

- Touching `AnnotateView.tsx`, `ManageTagsView.tsx`, `AIChat.tsx`, `JobLogsModal.tsx`, `LexemeSearchBlock.tsx`, `TranscriptionLanesControls.tsx`, `referenceFormParsing.ts` — extracted, leave alone
- The remaining ParseUI orchestrator logic — separate later pass
- Any behavior change, prop signature change, store mutation
- Touching `python/`

## Procedure

1. **Refetch first** — `git fetch origin && git checkout -B feat/parseui-extract-compare-helpers origin/main`. Main is moving fast (was at `4ffb31dd6f`, now at `a7fee2a19b` last I checked).
2. **Verify usage scope before placing helpers in shared/**:
   ```
   $ grep -rn "Pill\|SectionCard" src/ --include "*.tsx"
   ```
   If `Pill` or `SectionCard` is only used inside Compare-mode files, place in `src/components/compare/UIPrimitives.tsx` instead. If used cross-mode, `src/components/shared/UIPrimitives.tsx` is correct.
3. **Cut + re-derive line numbers** via grep (don't trust this prompt's table):
   ```
   $ grep -n "const SimBar\|const CognateCell\|const COGNATE_COLORS\|const Pill\|const SectionCard" src/ParseUI.tsx
   ```
4. **Move each helper** verbatim into its new file. Add `export` keywords. No logic changes.
5. **Update ParseUI.tsx imports**:
   ```ts
   import { CognateCell, SimBar } from './components/compare/CognateCell';
   import { Pill, SectionCard } from './components/shared/UIPrimitives';
   ```
   (Adjust paths if grep showed different placement.)
6. **Add paired tests** — one `it()` per scenario, hoisted-mock pattern from `parse-vitest-hoisted-store-mocks` skill:
   - `CognateCell.test.tsx`: render with high/low/null similarity, color mapping correctness, click handler dispatch
   - `UIPrimitives.test.tsx`: `Pill` render with each tone (slate/emerald/indigo); `SectionCard` render with title + aside + children
7. **Run gates**: `npm run typecheck`, `npm run test -- --run`, `npm run build`. All must be green. `ParseUI.test.tsx` still green.
8. **Browser regression** — open Compare mode, scroll through the concept × speaker table, verify `CognateCell` color/SimBar render unchanged. Verify any panel using `SectionCard` looks identical. **Screenshot of Compare table in PR body.** No screenshot needed for `Pill` / `UIPrimitives` since they're trivial render.

## Acceptance

- ParseUI.tsx down ~115 LoC (target: 3422 if branched from current 3537 main; will compose with the merge wave)
- 2 new files (or 3, depending on the `Pill`/`SectionCard` placement decision)
- Each new file has a paired test ≥40 LoC, green
- All existing tests pass without modification
- Browser screenshot of Compare table in PR body
- Coordinator (parse-gpt) reviews and merges; do not self-merge

## What this still leaves unfinished

After this PR + #69 + #71 + #73 all merge, ParseUI.tsx will be ~2380 LoC. To hit ≤1800, **at least one more pass** is needed — likely the residual ParseUI orchestrator's internal sub-handlers, modal-management logic, and any inline JSX blocks that should be sub-components. Do **not** start that pass in this handoff. Coordinator will queue it once this one lands.

## Conventions

- One commit per logical step (extract, fix imports, add tests)
- PR title: `refactor(parseui): extract Compare-mode helpers (SimBar, CognateCell, Pill, SectionCard)`
- Co-author line: `Co-Authored-By: parse-builder <noreply@anthropic.com>`
- Do not merge your own PR
- One PR for all four helpers (don't split — they're small and related)

## Out-of-band notes

- This PR's region (~lines 531–681 of pre-wave ParseUI.tsx) is **not** touched by #69, #71, or #73. So conflict risk is low. If you finish before the wave lands and main shifts again, just rebase as you did for #71/#73.
- If you discover any of the four helpers is also used by Annotate-mode (e.g., `Pill` shows up in Annotate too), flag in PR body — that affects the correct destination file.
- After this lands, the *next* parse-builder handoff (TBD) will likely target the residual ParseUI orchestrator. Don't plan ahead in this PR.
