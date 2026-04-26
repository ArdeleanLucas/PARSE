---
agent: parse-builder
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #79 (Compare helpers extraction) should land first to avoid line-number churn
  - Or: branch from current origin/main and accept that #79's merge will compose cleanly (different region)
related_skills:
  - parse-react-shell-refactor-planning
  - parse-react-shell-refactor-execution
  - parse-vitest-hoisted-store-mocks
  - test-driven-development
---

# parse-builder follow-on — ParseUI.tsx orchestrator pass (close to ≤1800 LoC)

**Why this exists:** After #71 + #73 + #79 land, ParseUI.tsx will be ~2229 LoC. The original PR #58 target was ≤1800. Remaining gap: ~429 LoC. The bulk of the file is now the `ParseUI()` orchestrator function itself (lines 520+, ~2160 LoC at PR #79 branch state). Component-extraction has been mined out; the next pass is **hook + utility extraction** from the orchestrator.

This is a more architectural pass than the prior component extractions — splitting orchestrator state into hooks is more error-prone. Expect more conflict resolution and more careful test scaffolding. Take it slower than the prior PRs.

## Working environment

```
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...   # --repo mandatory
```

Per AGENTS.md (PR #74 merged) — three prior wrong-repo PRs already documented.

## Scope

### In scope (3 PRs, sequential because they touch the same orchestrator state)

**PR A — Lift pure helpers + utilities to src/lib/** (~180 LoC reduction, lowest risk)

- `buildSpeakerForm` (~98 LoC, lines ~193 on current main) → `src/lib/speakerForm.ts`
- Small utilities in lines ~111–191 → `src/lib/parseUIUtils.ts`:
  - `isInteractiveHotkeyTarget`
  - `overlaps`
  - `deriveAudioUrl`
  - `conceptMatchesIntervalText`
  - `getConceptStatus`
  - `isRecord`
  - `readTextBlob`
- Keep `pickOrthoIntervalForConcept` re-exported from ParseUI.tsx (it's already a public re-export per the PR #58 contract; do not rename)

These are pure functions with no React/store coupling. Lift verbatim, add `export` keywords, paired test file `src/lib/parseUIUtils.test.ts` covering each function.

**PR B — Extract `useParseUIModals` hook** (~150–200 LoC reduction, medium risk)

The orchestrator manages 6+ modal states inline:

- `clefModalOpen` + `clefInitialTab` (CLEF config)
- `runModal` (TranscriptionRunModal)
- `importModalOpen` (Speaker import)
- `offsetModalOpen` (OffsetAdjustment)
- `batchReportOpen` (BatchReportModal)
- `clefSourcesReportOpen` (ClefSourcesReportModal)

Each has an `open*`/`close*` handler pair. Extract into a single `useParseUIModals` hook in `src/hooks/useParseUIModals.ts`:

```ts
interface UseParseUIModalsResult {
  clef: { isOpen: boolean; initialTab: ClefConfigModalTab; open: (tab?: ClefConfigModalTab) => void; close: () => void };
  run: { state: TranscriptionRunConfirm | null; open: (title: string, fixedSteps?: PipelineStepId[]) => void; close: () => void };
  import: { isOpen: boolean; open: () => void; close: () => void };
  // ... rest
}
```

Test file: `src/hooks/__tests__/useParseUIModals.test.ts` covering each modal's open/close lifecycle + the parametrized open variants (`openClefModal('contact-langs')` etc.).

**PR C — Extract `useParseUIPipeline` hook + handler cluster** (~200–300 LoC reduction, higher risk)

The pipeline/batch state cluster around lines ~825–870 on current main:

- `runModal` interaction with batch pipeline
- Batch report state propagation
- TranscriptionRunModal step selection
- Pipeline error surfacing

Extract into `src/hooks/useParseUIPipeline.ts`. This is the trickiest pass because pipeline state intersects with modal state from PR B, so this PR must come AFTER PR B and consume `useParseUIModals` cleanly.

Test file: `src/hooks/__tests__/useParseUIPipeline.test.ts` with mocked `useBatchPipelineJob` + `useComputeJob`.

### Out of scope

- Touching `AnnotateView.tsx`, `ManageTagsView.tsx`, `AIChat.tsx`, `JobLogsModal.tsx`, `LexemeSearchBlock.tsx`, `TranscriptionLanesControls.tsx`, `referenceFormParsing.ts`, `CognateCell.tsx`, `UIPrimitives.tsx` — already extracted, leave alone
- Renaming public exports (`pickOrthoIntervalForConcept`, `parseReferenceFormList`, `resolveReferenceFormLists`, `resolveFormSelection`, `ReferenceFormEntry`)
- Changing prop signatures of any extracted component
- Touching `python/` or any backend file
- The next-biggest frontend monolith `TranscriptionLanes.tsx` (943 LoC) — separate task after this lands

## Procedure (per PR — adapt to PR-specific scope)

1. **Refetch first** — `git fetch origin && git checkout -B feat/parseui-<slug> origin/main`. Main keeps moving.
2. Re-derive line numbers via grep — do not trust this prompt's line numbers; the merge wave is shifting them every hour.
3. Cut + lift verbatim. Add `export` for any previously-private symbols the new test file needs.
4. Add paired test file. One `it()` block per scenario; hoisted-mock pattern from `parse-vitest-hoisted-store-mocks` skill required for any test that mocks a Zustand store.
5. Update ParseUI.tsx imports.
6. Run gates: `npm run typecheck && npm run test -- --run && npm run build`. ParseUI.test.tsx must stay green.
7. Browser regression — boot dev server, exercise the affected surface (modals open/close, pipeline run, etc.), screenshot in PR body.

## Acceptance (cumulative across all 3 PRs)

- `wc -l src/ParseUI.tsx` ≤ **1800** (the original PR #58 target)
- `src/lib/speakerForm.ts` exists with paired test
- `src/lib/parseUIUtils.ts` exists with paired test
- `src/hooks/useParseUIModals.ts` exists with paired test
- `src/hooks/useParseUIPipeline.ts` exists with paired test
- All existing tests pass without modification
- Browser screenshot per PR showing the affected surface working unchanged
- Coordinator (parse-gpt) reviews and merges; do not self-merge

## If you can't hit ≤1800 cleanly

If after PR A + B + C, ParseUI.tsx is still above 1800 LoC by more than ~50 lines, **stop and surface it to coordinator rather than continuing to micro-extract.** The orchestrator may legitimately need ~1900–2000 LoC to coordinate 3 modes + 6 modals + AI chat + pipelines, in which case the ≤1800 target was over-aggressive and we should accept the floor and move on to other monoliths (`TranscriptionLanes.tsx`, `BatchReportModal.tsx`, etc.).

Do not split the orchestrator into mode-specific shells (`ParseUIAnnotate.tsx`, `ParseUICompare.tsx`, `ParseUITags.tsx`) without explicit coordinator approval — that's a redesign, not an extraction, and changes the shell architecture in ways the parity work depends on.

## Conventions

- One commit per logical step
- PR title format: `refactor(parseui): <action>` (e.g., `refactor(parseui): lift pure helpers to src/lib`)
- Co-author line: `Co-Authored-By: parse-builder <noreply@anthropic.com>`
- Do not merge your own PRs

## Out-of-band notes

- **PR ordering matters**: PR A (pure lifts) → PR B (modals hook) → PR C (pipeline hook). PR C consumes PR B; if you ship them out of order you'll regret the conflict resolution.
- **Don't merge PRs in parallel for this pass** — orchestrator state is interdependent. Wait for each to land before opening the next.
- **If the dev server breaks during a PR**, prefer narrowing scope (split into smaller PRs) over papering over with workarounds. The orchestrator is fragile.
- After this lands and ≤1800 is hit (or the floor is found), the next parse-builder task is `TranscriptionLanes.tsx` (943 LoC, next-biggest annotate-mode component). Do not start that here.
