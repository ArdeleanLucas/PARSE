# ParseUI shell refactor execution plan (current-state, behavior-preserving)

## TL;DR

Refactor `src/ParseUI.tsx` as a **shell-only extraction**, not a frontend-wide tree reset.
Keep the current PARSE repo as the oracle, preserve the React/Vite + Zustand architecture already on `origin/main`, and extract only the unified-shell surfaces that still live inside `ParseUI.tsx`.

Recommended direction:
1. freeze the current behavior with the existing 41-file / 283-test baseline,
2. extract small stable shell islands first,
3. move offset and shell selection/filter logic into dedicated hooks,
4. move inline mode views into `src/components/parse/**`,
5. finish with an orchestration-only `ParseUI.tsx`.

This plan is for **Phase 0 / lane setup only**. No PARSE source implementation is started here.

---

## Verified repo / baseline facts

### Canonical repo + branch state
- Canonical repo inspected: `/home/lucas/gh/ardeleanlucas/parse`
- User warning verified: the main checkout is not clean:
  - `?? .hermes/`
  - `?? config/cache/`
- Therefore implementation work should not use that checkout directly.
- Fresh worktree created from latest `origin/main`:
  - worktree: `/home/lucas/gh/worktrees/PARSE/parseui-shell-refactor-plan`
  - branch: `docs/parseui-shell-refactor-plan`
  - base commit: `b26c71f docs: refresh PARSE docs for PRs 214-219 (#220)`
- Latest `origin/main` history in the fresh worktree:
  - `b26c71f docs: refresh PARSE docs for PRs 214-219 (#220)`
  - `1547b60 docs: plan separate rebuild path from option 1 to option 3 (#223)`
  - `2f8c0cc feat(clef): academic citations in Sources Report (#222)`

### Required validation baseline (re-run in the fresh worktree)
- `npm run test -- --run` ✅
  - `41` test files
  - `283` tests passed
- `./node_modules/.bin/tsc --noEmit` ✅
- Non-blocking stderr observed but passing:
  - React Router future-flag warnings in annotate tests
  - `tagStore` localStorage warnings in `storePersistence.test.ts`

### Current monolith pressure points confirmed live
- `src/ParseUI.tsx` — `5328` lines
- `src/ParseUI.test.tsx` — `940` lines / `29` tests
- repo-wide pressure points from the existing assessment still hold:
  - `python/server.py` — `8962` lines
  - `python/ai/chat_tools.py` — `6408` lines
  - `src/ParseUI.tsx` — `5328` lines

### Current ParseUI structure confirmed live
Inline components still inside `src/ParseUI.tsx`:
- `AIChat` — starts at line `703`
- `ManageTagsView` — starts at line `1314`
- `AnnotateView` — starts at line `1541`
- main exported `ParseUI` — starts at line `2112`

Live shell hotspots inside `ParseUI`:
- shell bootstrap + state assembly — `2112+`
- top bar / mode / actions / batch / offset chip — around `3225-3667`
- concept sidebar — around `3687-3780`
- compare-mode inline body — around `3848-4255`
- right control panel — around `4272-4645`
- modal cluster — around `4666-4850+`

### Existing extracted surfaces to reuse, not reinvent
Already standalone and should stay authoritative:
- `src/components/shared/TranscriptionRunModal.tsx` — `792` lines
- `src/components/shared/BatchReportModal.tsx` — `843` lines
- `src/components/compare/CommentsImport.tsx` — `140` lines
- `src/components/compare/SpeakerImport.tsx` — `207` lines
- `src/components/compare/LexemeDetail.tsx` — `388` lines
- `src/components/compute/ClefConfigModal.tsx` — `622` lines
- `src/components/compute/ClefSourcesReportModal.tsx` — `563` lines

### Existing adjacent surfaces inspected
Annotate surfaces:
- `AnnotateMode.tsx`, `AnnotationPanel.tsx`, `ChatPanel.tsx`, `OnboardingFlow.tsx`, `RegionManager.tsx`, `SuggestionsPanel.tsx`, `TranscriptPanel.tsx`, `TranscriptionLanes.tsx`

Compare surfaces:
- `CompareMode.tsx`, `ConceptTable.tsx`, `CognateControls.tsx`, `BorrowingPanel.tsx`, `EnrichmentsPanel.tsx`, `SpeakerImport.tsx`, `CommentsImport.tsx`, `LexemeDetail.tsx`, `ContactLexemePanel.tsx`, `TagManager.tsx`

Shared / compute / hooks / stores:
- shared primitives + `index.ts`
- compute CLEF modals + summary banner
- hooks including `useAnnotationSync`, `useBatchPipelineJob`, `useChatSession`, `useComputeJob`, `useExport`, `useImportExport`, `useSpectrogram`, `useSuggestions`, `useWaveSurfer`
- stores: `annotationStore`, `configStore`, `enrichmentStore`, `playbackStore`, `tagStore`, `transcriptionLanesStore`, `uiStore`

### Existing ParseUI regression coverage confirmed live
`src/ParseUI.test.tsx` already covers these high-value behaviors:
- mode switching (`a/c/t` and dropdown)
- annotate concept navigation via arrow keys
- compare speaker import modal entry
- compare flag / accept actions
- compare reference forms and CLEF rendering branches
- transcription action menu entry points + modal opening
- compare notes persistence
- provider badge restoration in AI chat
- ortho prefill from `ortho_words`

Coverage is useful but incomplete for the upcoming shell breakup.
The main gaps are around the offset workflow, right-panel speaker-selection invariants, and some modal orchestration boundaries.

---

## Architectural stance to preserve

### Frontend shell stance
Preserve the current unified-shell architecture and adapt the target tree to the live code.
The target `src/components/parse/**` tree is a **design input**, not law.

### Repo-wide stance
Preserve **Option 1: Domain-Preserving Modularization** from the verified whole-repo assessment:
- frontend keeps `annotate`, `compare`, `compute`, `shared`, plus a small shell layer
- backend remains untouched in this phase
- do **not** treat this refactor as a monorepo/package reset
- do **not** jump to Option 3 unless parity is already earned later

### Hard rules preserved from current PARSE reality
- no bare `fetch()` calls; API traffic remains in `src/api/client.ts`
- no `window.PARSE`
- Zustand remains the data-state source of truth
- `AnnotationInterval.start/end` must remain immutable once set
- concept IDs remain stable identifiers
- TypeScript must stay green
- new hooks/components get co-located tests
- preserve keyboard shortcuts, audio behavior, export paths, and compare workflows

---

## Recommended architecture

### Repo-wide architecture options considered
This shell plan is local to `src/ParseUI.tsx`, but it is grounded in the repo-wide planning skill's required 3-option comparison.

#### Option 1 — Domain-Preserving Modularization (recommended)
**Pros**
- safest migration path for thesis-critical PARSE behavior
- lowest import/path churn
- best fit for staged PRs
- preserves the current frontend/backend mental model
- lets the frontend shell shrink without forcing backend churn now

**Cons**
- less visually uniform than a full repo redesign
- keeps some historical naming in place
- requires discipline so new shell/app layers stay thin

#### Option 2 — Full Feature-Slice Architecture
**Pros**
- strong end-to-end feature ownership
- elegant on paper if PARSE is reorganized around product flows

**Cons**
- much higher churn
- harder to preserve current behavior while migrating
- stresses tests, imports, docs, and runtime assumptions at once

#### Option 3 — Platform / Package-Oriented Split
**Pros**
- cleanest long-term platform architecture
- strongest package/contract separation

**Cons**
- highest migration cost
- not appropriate as the first move during thesis-critical stability work
- massively expands regression surface across tooling and deployment

### Recommended option and why
For the whole repo, this plan keeps **Option 1 — Domain-Preserving Modularization** as the explicit recommendation.
That fits PARSE's current code reality because the repo already has meaningful `annotate`, `compare`, `compute`, `shared`, `hooks`, `stores`, `ai`, `compare`, `external_api`, `adapters`, and `workers` domains. The immediate problem is the `ParseUI.tsx` shell monolith, not a missing top-level package split.

### Shell target
Use `src/components/parse/**` only for **unified-shell-specific composition**.
Do not migrate existing annotate/compare/shared/compute domain components into `parse/` unless they are truly shell-specific wrappers.

```text
src/
├── components/
│   ├── annotate/          # existing domain components remain canonical
│   ├── compare/           # existing domain components remain canonical
│   ├── compute/           # existing domain components remain canonical
│   ├── shared/            # existing shared components remain canonical
│   └── parse/             # new unified-shell extraction layer only
│       ├── ParseLayout.tsx
│       ├── ParseHeader.tsx
│       ├── ConceptSidebar.tsx
│       ├── CompareView.tsx
│       ├── RightPanel.tsx
│       ├── AIChat.tsx
│       ├── AnnotateView.tsx
│       ├── ManageTagsView.tsx
│       └── modals/
│           └── OffsetAdjustmentModal.tsx
├── hooks/
│   ├── useOffsetState.ts
│   ├── useConceptFiltering.ts
│   └── useSpeakerSelection.ts
└── ParseUI.tsx
```

### What should remain outside `parse/`
Keep these where they are and import them from the shell layer:
- `components/shared/TranscriptionRunModal.tsx`
- `components/shared/BatchReportModal.tsx`
- `components/compare/CommentsImport.tsx`
- `components/compare/SpeakerImport.tsx`
- `components/compare/LexemeDetail.tsx`
- `components/compute/ClefConfigModal.tsx`
- `components/compute/ClefSourcesReportModal.tsx`

### Why this architecture fits the live code
- `ParseUI.tsx` already imports stable domain components from `annotate`, `compare`, `shared`, and `compute`
- the monolith pressure is in shell composition and orchestration, not in a missing global namespace
- the shell owns mode switching, layout, concept navigation, offset flow, modal wiring, and right-panel controls
- domain features like CLEF, SpeakerImport, CommentsImport, transcription runs, and LexemeDetail already have better homes

---

## Exact file ownership split

## parse-builder lane (write owner for the shell refactor PR)
Primary implementation ownership if Lucas authorizes execution:
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/parse/ParseLayout.tsx`
- `src/components/parse/ParseHeader.tsx`
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/CompareView.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/components/parse/AIChat.tsx`
- `src/components/parse/AnnotateView.tsx`
- `src/components/parse/ManageTagsView.tsx`
- `src/components/parse/modals/OffsetAdjustmentModal.tsx`
- `src/hooks/useOffsetState.ts`
- `src/hooks/useConceptFiltering.ts`
- `src/hooks/useSpeakerSelection.ts`
- co-located tests for the new parse shell files

## parse-gpt lane (parallel lane recommendation)
For this shell PR, keep parse-gpt **out of the write path** for shell-owned files.
Recommended parallel lane during implementation:
- read-only review of `annotate`, `compare`, `shared`, and `compute` dependencies touched by the extraction
- propose test-gap notes and downstream follow-up PRs, but do not edit the shell PR's owned files
- if Lucas explicitly expands the parallel split later, parse-gpt can own **follow-up** domain-specific cleanup PRs, not this shell-extraction PR

Concrete parse-gpt lane for this phase:
- no writes in the shell PR
- optional read-only audit notes on:
  - compare integration assumptions
  - annotate keyboard/audio invariants
  - modal interface stability
  - test coverage gaps outside the shell layer

## Shared read-only surfaces during this shell refactor
These may be read and depended on, but should not be edited inside the shell-extraction PR unless Lucas explicitly broadens scope:
- `src/api/client.ts`
- `src/api/types.ts`
- `src/stores/*`
- `src/components/annotate/*`
- `src/components/compare/*`
- `src/components/shared/*`
- `src/components/compute/*`
- `python/**`

This split minimizes merge conflict risk and preserves the shell/domain boundary.

---

## Exact file list for the planned refactor

### New files to create
- `src/components/parse/ParseLayout.tsx`
- `src/components/parse/ParseHeader.tsx`
- `src/components/parse/ConceptSidebar.tsx`
- `src/components/parse/CompareView.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/components/parse/AIChat.tsx`
- `src/components/parse/AnnotateView.tsx`
- `src/components/parse/ManageTagsView.tsx`
- `src/components/parse/modals/OffsetAdjustmentModal.tsx`
- `src/hooks/useOffsetState.ts`
- `src/hooks/useConceptFiltering.ts`
- `src/hooks/useSpeakerSelection.ts`
- co-located tests:
  - `src/components/parse/ParseHeader.test.tsx`
  - `src/components/parse/ConceptSidebar.test.tsx`
  - `src/components/parse/CompareView.test.tsx`
  - `src/components/parse/RightPanel.test.tsx`
  - `src/components/parse/AIChat.test.tsx`
  - `src/components/parse/AnnotateView.test.tsx`
  - `src/components/parse/ManageTagsView.test.tsx`
  - `src/components/parse/modals/OffsetAdjustmentModal.test.tsx`
  - `src/hooks/__tests__/useOffsetState.test.ts`
  - `src/hooks/__tests__/useConceptFiltering.test.ts`
  - `src/hooks/__tests__/useSpeakerSelection.test.ts`

### Existing files to modify
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`

### Existing files to reuse without relocation
- `src/components/shared/TranscriptionRunModal.tsx`
- `src/components/shared/BatchReportModal.tsx`
- `src/components/compare/CommentsImport.tsx`
- `src/components/compare/SpeakerImport.tsx`
- `src/components/compare/LexemeDetail.tsx`
- `src/components/compute/ClefConfigModal.tsx`
- `src/components/compute/ClefSourcesReportModal.tsx`

---

## Staged execution order

### Stage 0 — Baseline freeze and test gap review
Goal: confirm the current shell behavior before moving code.

Actions:
1. branch/worktree from latest `origin/main`
2. run the existing validation gates
3. review `src/ParseUI.test.tsx` against the actual shell hotspots
4. add only missing safety-net tests before the first extraction

Mandatory test gaps to close first:
- offset status chip + modal phase transitions
- right-panel speaker selection behavior in annotate and compare
- comments import modal path if not already shell-covered end-to-end
- batch report visibility + rerun from shell-level entry points
- LingPy export trigger path from the shell

### Stage 1 — Small stable UI islands
Goal: extract low-churn shell surfaces with limited business logic.

Order:
1. `ConceptSidebar.tsx`
2. `RightPanel.tsx`

Why first:
- both are cohesive shell surfaces already visible in narrow line ranges
- both reduce immediate `ParseUI` size without forcing deep domain rewiring
- both can stay prop-driven against existing stores and callbacks

### Stage 2 — Offset workflow as a hook + modal pair
Goal: remove the largest shell-specific state machine from `ParseUI` without touching domain stores.

Order:
1. `useOffsetState.ts`
2. `components/parse/modals/OffsetAdjustmentModal.tsx`
3. rewire the header chip + modal cluster to the hook

Ownership of `useOffsetState` should include:
- phase state
- progress / error state
- manual anchors
- consensus derivation
- detect/apply/manual submit flows
- crash-log handoff data
- protected-lexeme derivation inputs or memoized outputs

### Stage 3 — Mode views
Goal: move inline mode bodies out of the root shell.

Order:
1. `ManageTagsView.tsx` (move-only extraction)
2. `AIChat.tsx` (move-only extraction)
3. `AnnotateView.tsx` (move-only extraction)
4. `CompareView.tsx` (the only heavier extraction in this stage)

Notes:
- `ManageTagsView`, `AIChat`, and `AnnotateView` already exist inline as coherent components
- `CompareView` is currently the main non-extracted view body and should become the biggest new file under `components/parse/`
- existing compare/compute/shared child components remain imported, not re-homed

### Stage 4 — Header/layout shell
Goal: separate shell composition from feature rendering.

Order:
1. `ParseHeader.tsx`
2. `ParseLayout.tsx`
3. `useConceptFiltering.ts`
4. `useSpeakerSelection.ts`

Notes:
- `ParseHeader` owns mode dropdown, actions menu, reviewed progress, batch chip, offset chip, and theme toggle UI only
- `ParseLayout` owns the 3-column shell composition only
- `useConceptFiltering` owns search / sort / tag filter / filtered concepts / survey-order decisions
- `useSpeakerSelection` owns annotate-vs-compare selection rules, active speaker synchronization, picker state, and import-complete behavior

### Stage 5 — Final orchestration-only `ParseUI.tsx`
Goal: reduce `ParseUI.tsx` to shell orchestration, data assembly, and wiring.

Target outcome:
- bootstrap + store access
- derived shell state
- callback wiring
- modal open/close orchestration
- layout composition
- no large inline JSX regions
- no shell-specific state machines embedded inline

A hard line-count target is less important than achieving a readable orchestration shell with preserved behavior.

---

## Validation strategy

### Always-on gates after every extraction stage
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`

### Shell-specific regression checklist
These behaviors must stay green throughout the staged extraction:
- mode switching between annotate / compare / tags
- arrow-key concept navigation outside interactive inputs
- annotate undo / redo shortcuts
- right-panel speaker selection in annotate and compare
- offset status chip and modal phase flow
- annotate anchor-capture path
- transcription action menu opening the run modal
- batch report visibility and rerun flow
- compare reference-form rendering and speaker-form rendering
- comments import modal path
- LingPy export trigger path
- AI chat render path, including markdown rendering and provider badge state

### Test strategy by layer
#### Keep in `src/ParseUI.test.tsx`
Retain shell-level integration assertions for:
- mode switching
- concept navigation
- modal entry points
- run/batch/report orchestration
- export entry points
- cross-panel interactions

#### Add co-located component tests
Add focused tests for:
- `ConceptSidebar`
- `RightPanel`
- `ParseHeader`
- `CompareView`
- `AnnotateView`
- `ManageTagsView`
- `AIChat`
- `OffsetAdjustmentModal`

#### Add hook tests
Add isolated tests for:
- `useOffsetState`
- `useConceptFiltering`
- `useSpeakerSelection`

This split prevents `ParseUI.test.tsx` from becoming the only regression net while the shell is decomposed.

## Acceptance criteria

The plan is only implementation-ready when all of these are explicit and preserved:
- `ParseUI.tsx` ends as a controller/orchestration shell, not a render monolith
- the implementation keeps exact validation commands front-and-center:
  - `npm run test -- --run`
  - `./node_modules/.bin/tsc --noEmit`
- browser QA targets are named for all 3 workstation modes:
  - Annotate: waveform, selected speaker, region actions, offset capture path
  - Compare: concept table, speaker forms, CLEF section, cognate actions
  - Tags: create/rename/assign flow
  - global shell: mode switcher, actions menu, right drawer, AI dock
- the non-regression list remains explicit:
  - offset flow
  - keyboard shortcuts
  - right-panel speaker selection
  - exports
  - compare workflows
  - chat/auth state
- the plan remains staged into small, reviewable slices rather than a one-pass rewrite

---

## Risk table

| Risk | Why it matters in current code | Severity | Mitigation |
|---|---|---:|---|
| Offset workflow regression | The offset flow is distributed across header chip, modal UI, job polling, manual anchors, and protected-lexeme messaging | High | Extract as `useOffsetState` + modal pair, not as raw JSX-only moves |
| Speaker-selection drift | `selectedSpeakers`, `speakerPicker`, `useUIStore`, and `usePlaybackStore` are coordinated differently in annotate vs compare | High | Centralize in `useSpeakerSelection`; add explicit annotate/compare tests |
| Compare-view extraction accidentally touches domain components | `CompareView` currently orchestrates many imported compare/compute pieces | High | Keep compare/compute components read-only; extract only shell composition and callbacks |
| Keyboard shortcut regressions | `ParseUI.test.tsx` covers some hotkeys but not every shell boundary | High | Expand shell tests before extraction; keep integration tests in `ParseUI.test.tsx` |
| Modal orchestration breakage | Transcription, batch report, speaker import, CLEF, comments import, and offset all coexist in one modal cluster | High | Keep existing modal components authoritative; move only shell-level open/close wiring |
| Overfitting to the requested target tree | The requested structure is not perfectly aligned with the live codebase | Medium | Treat `parse/` as a shell layer only; do not re-home stable domain components |
| Line-count-driven refactor pressure | Forcing `ParseUI.tsx` under an arbitrary threshold may cause unsafe abstraction | Medium | Optimize for behavior-preserving readability, not a numeric line target |
| Scope creep into stores/API/backend | Those surfaces are shared and currently out of lane | High | Mark them read-only for this PR unless Lucas explicitly expands scope |

---

## Open questions / assumptions

### Assumptions used in this plan
- this PR remains a shell-refactor PR, not a contract/API/store PR
- existing annotate/compare/shared/compute components remain canonical and are reused as dependencies
- `src/ParseUI.test.tsx` stays as the top-level shell integration suite
- no backend changes are required for the shell extraction itself

### Open questions to resolve before implementation starts
1. Should `CommentsImport` remain wrapped by a generic shared `Modal` from `ParseUI`, or should a shell-local wrapper component own that composition?
2. Should `useSpeakerSelection` own import-complete side effects entirely, or should `ParseUI` remain the owner of import completion and pass the result down?
3. Should `AIChat` move as-is first, or should its auth/provider/session sub-sections be split in a later follow-up PR rather than in the shell refactor?
4. Is Lucas okay with `ParseUI.tsx` remaining above 350 lines if the result is a clean orchestration shell with safer boundaries?
5. Does Lucas want parse-gpt assigned a write lane in a separate follow-up PR after this shell split, or should parse-gpt remain read-only / reviewer on the shell work itself?

---

## Proposed next action

If Lucas authorizes implementation, the next action should be:

1. open a new implementation worktree from latest `origin/main`,
2. add the missing Stage-0 shell regression tests first,
3. implement Stage 1 only (`ConceptSidebar` + `RightPanel`),
4. stop and re-run the full gates before starting the offset extraction.

That gives the refactor its safest first slice and preserves a clean parallel boundary.