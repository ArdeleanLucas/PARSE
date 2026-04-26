# parse-builder — next task: ParseUI.tsx structural cracks

**Lane:** Agent A (frontend)
**Date queued:** 2026-04-26
**Rebuild oracle SHA at queue time:** `f9aa3db1aa`
**Live oracle SHA at queue time:** `ArdeleanLucas/PARSE@0951287a81`
**Branch from:** `origin/main`
**Estimated PR count:** 3 (one per extracted view; do not bundle)

---

## Why this task

`src/ParseUI.tsx` is still 4418 LoC on `origin/main`. Prior frontend PRs (#3, #7, #11) extracted shell islands (`ConceptSidebar`, `RightPanel`, `OffsetAdjustmentModal`) and shaved ~17% off the original 5328-line monolith, but the central body of ParseUI.tsx is now three large React components inlined into one file:

| Component | Approx. lines in ParseUI.tsx | Approx. LoC |
|---|---:|---:|
| `AIChat` | 729 → 1322 | ~593 |
| `ManageTagsView` | 1340 → 1554 | ~214 |
| `AnnotateView` | 1567 → 4178 | ~2611 |

Until these are pulled out, the file cannot be safely modified by parallel lanes (it touches Annotate, Compare, AI/chat, and Tags surfaces simultaneously) and the Option-1 parity work cannot proceed cleanly. This task brings ParseUI.tsx under 2500 LoC and gives each extracted view its own test file.

This is a **structural extraction**, not a redesign. Behavior must remain byte-equivalent against the live oracle for every flow listed in `docs/plans/option1-parity-inventory.md` §5.1 (Annotate, Compare, Tags) and §5.2 (AI/chat).

---

## Scope

### In scope

1. Extract `AIChat` (lines ~729–1322) → `src/components/shared/AIChat.tsx` + `src/components/shared/AIChat.test.tsx`.
2. Extract `ManageTagsView` (lines ~1340–1554) → `src/components/compare/ManageTagsView.tsx` + `.test.tsx`.
3. Extract `AnnotateView` (lines ~1567–4178) → `src/components/annotate/AnnotateView.tsx` + `.test.tsx`. Extract supporting helpers `JobLogsModal`, `LexemeSearchBlock`, `TranscriptionLanesControls` (lines ~4179–4500) into the same file *only if* they are exclusively used by AnnotateView; otherwise put them in their own files in the same dir.
4. Update `src/ParseUI.tsx` imports and remove the inlined definitions.
5. Move type/interface declarations (`AIChatProps`, `ManageTagsProps`, `AnnotateViewProps`, `ChatMessage`, `AIProvider`, `AIConnectionView`, `TestStatus`) into the extracted files.
6. Move tightly-scoped local constants (`PROVIDER_META`, `QUICK_ACTIONS`, `SWATCHES`, `LANE_ORDER`, `LANE_DISPLAY`) into the file that uses them.

### Out of scope

- Behavior changes, prop signature changes, store-shape changes, API contract changes.
- Any rename of public exports re-exported from `ParseUI.tsx` (`pickOrthoIntervalForConcept`, `parseReferenceFormList`, `resolveReferenceFormLists`, `resolveFormSelection`, `ReferenceFormEntry` type) — these stay re-exported from ParseUI.tsx for the duration of this task to avoid breaking any test imports.
- Refactoring `useWaveSurfer`, `useSpectrogram`, `useChatSession`, `useAnnotationSync`, `useComputeJob`, `useActionJob`, `useBatchPipelineJob` — already extracted, leave alone.
- Touching `src/components/parse/`, `src/components/compute/`, `src/components/compare/` files other than the new `ManageTagsView.tsx`.
- Touching `python/` at all.

---

## Sequence (one PR per step, in order)

### Step 1 — Extract `AIChat` (smallest, lowest blast radius)

**Branch:** `feat/parseui-extract-aichat`
**Target file:** `src/components/shared/AIChat.tsx`
**Test file:** `src/components/shared/AIChat.test.tsx`

Procedure:
1. Cut the `AIChat` component, its props interface, and its private types (`AIProvider`, `AIConnectionView`, `TestStatus`, `ChatMessage`, `PROVIDER_META`, `QUICK_ACTIONS`, `resolveAuthProvider`) into the new file.
2. Re-import from ParseUI.tsx: `import { AIChat } from './components/shared/AIChat';`.
3. Move any AIChat-only imports (`saveApiKey`, `getAuthStatus`, `pollAuth`, `startAuthFlow`, `useChatSession`, `ChatMarkdown`) out of ParseUI.tsx if they are not used elsewhere in the file. Verify with grep before removing.
4. Add unit tests for: provider switch (xAI ↔ OpenAI), auth flow status transitions, message render with `ChatMarkdown`, minimize/restore, conceptName display, send-on-enter behavior.
5. Run `npm run test` and `npm run typecheck`. Both must be green.
6. Run dev server + browser regression: open Annotate, open Chat panel, switch providers, send a message, minimize/restore. Capture screenshot evidence in PR description.

Acceptance: `wc -l src/ParseUI.tsx` shows reduction of ~590 lines. New file ≤620 LoC. Test file ≥100 LoC and green.

### Step 2 — Extract `ManageTagsView`

**Branch:** `feat/parseui-extract-manage-tags-view`
**Target file:** `src/components/compare/ManageTagsView.tsx`
**Test file:** `src/components/compare/ManageTagsView.test.tsx`

Procedure:
1. Cut `ManageTagsView`, `ManageTagsProps`, and `SWATCHES` into the new file.
2. Re-import from ParseUI.tsx.
3. Verify `useTagStore` selector usage is unchanged.
4. Tests cover: tag create/rename/delete/merge, swatch selection persistence, bulk-state changes, empty state.
5. Run gates as Step 1.
6. Browser regression: open Compare → Manage Tags, exercise create/rename/delete/merge/bulk paths.

Acceptance: ParseUI.tsx down ~210 lines. New file ≤230 LoC. Test file ≥80 LoC and green.

### Step 3 — Extract `AnnotateView` (the big one)

**Branch:** `feat/parseui-extract-annotate-view`
**Target files:**
- `src/components/annotate/AnnotateView.tsx`
- `src/components/annotate/AnnotateView.test.tsx`
- `src/components/annotate/JobLogsModal.tsx` (if standalone — verify with grep)
- `src/components/annotate/LexemeSearchBlock.tsx` (verify standalone)
- `src/components/annotate/TranscriptionLanesControls.tsx` (verify standalone)

Procedure:
1. Identify shared closures and helpers used by `AnnotateView` and lift any that are private into the new file. List of suspects: `formatPlaybackTime`, `isInteractiveHotkeyTarget`, `overlaps`, `deriveAudioUrl`, `findAnnotationForConcept`. If used elsewhere in ParseUI.tsx, leave them as imports.
2. Cut `AnnotateView`, `AnnotateViewProps`, `LANE_ORDER`, `LANE_DISPLAY` into the new file.
3. Cut `JobLogsModal`, `LexemeSearchBlock`, `TranscriptionLanesControls` into appropriate sibling files. If any of them is exclusively imported by AnnotateView, co-locate it in `AnnotateView.tsx`; otherwise its own file.
4. Re-import from ParseUI.tsx.
5. Tests cover: prefill from stored annotations, save annotation, mark done, annotated/missing badge, region capture, STT request flow, lane visibility toggling, undo/redo, hotkey routing, JobLogsModal open/close, LexemeSearchBlock submit, captureOffsetAnchor toast.
6. Run gates as Step 1.
7. Browser regression: full Annotate workstation walkthrough — load speaker, edit interval, save, mark done, run STT for one interval, open JobLogs, search a lexeme. Capture screenshots and a short transcript-style description in PR.

Acceptance: ParseUI.tsx down ~2600 lines (final ParseUI.tsx ≤1800 LoC). AnnotateView ≤2700 LoC. Test file ≥250 LoC and green.

---

## Test gates (every PR)

Each PR must pass before requesting review:

- `npm run typecheck` — green
- `npm run test` — green, no skipped tests added
- `npm run build` — green (catches accidental import-cycle issues)
- ParseUI.test.tsx existing assertions still pass (no behavior regressions)
- Browser smoke test (procedure above) — screenshot in PR body

If a test in `ParseUI.test.tsx` references the inlined component by closure, lift that test into the new component's test file before extracting.

---

## Conventions

- One commit per logical operation (extract, fix imports, add tests, fix tests).
- PR title format: `refactor(parseui): extract <ComponentName> from ParseUI.tsx`.
- PR body must include: before/after `wc -l src/ParseUI.tsx`, screenshots from browser regression, list of any helpers that moved.
- Co-author line: `Co-Authored-By: parse-builder <noreply@anthropic.com>`.
- Do not merge your own PRs. Coordinator (parse-gpt) reviews and merges.

---

## Skill references

Use these installed Hermes skills:

- `parse-react-shell-refactor-planning` — for deciding co-location vs sibling-file boundaries when helpers are ambiguous
- `parse-react-shell-refactor-execution` — for the staged behavior-preserving extraction loop
- `parse-vitest-hoisted-store-mocks` — required when adding tests that mock `useAnnotationStore`, `useTagStore`, `useEnrichmentStore`, `useConfigStore`, `usePlaybackStore`, `useUIStore`, or `api/client`. Hoist failures will silently mis-mock.
- `test-driven-development` — write the new test file's structural cases before doing the extraction; use them to detect regressions during the cut.
- `parse-vitest-hoisted-store-mocks` — repeated because Zustand store mocks are the #1 cause of false-green Vitest runs in this repo.

---

## What "done" looks like at the end of all 3 PRs

- `wc -l src/ParseUI.tsx` ≤ 1800
- `src/components/shared/AIChat.tsx` exists with paired test
- `src/components/compare/ManageTagsView.tsx` exists with paired test
- `src/components/annotate/AnnotateView.tsx` exists with paired test
- All three PRs merged to `origin/main` of the rebuild repo
- ParseUI.test.tsx still green
- Browser regression: Annotate, Compare → Manage Tags, and AI Chat all behave identically to oracle

---

## Out-of-band notes

- The currently-checked-out branch on `/home/lucas/gh/tarahassistant/PARSE-rebuild` (`feat/parseui-shell-stage0-rebuild`) is stale (4 commits behind main). Branch from `origin/main` directly, not from local HEAD.
- Do not rebase prior open PRs (#36, #41, #43) — those are coordinator-owned. If they conflict with your extractions after merge, the coordinator will resolve.
- If you discover ParseUI.tsx contains dead code (unused helpers, unused imports), flag it in the PR body but do not delete in this task — schedule a separate cleanup PR after the three extractions land.
