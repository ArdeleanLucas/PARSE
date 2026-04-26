# ParseBuilder next task — compute-mode semantics audit

## Goal

Reconcile the Compare-mode compute drawer with the live `/api/compute/*` contract on current `origin/main` so PARSE sends explicit, academically honest payloads instead of generic type-only jobs.

## Why this is the right next task now

- The session-window handoff for 2026-04-26 confirmed `TarahAssistant/PARSE-rebuild` current `origin/main` is green at `7b33696`.
- PR #19 (`fix(annotate): prevent TranscriptionLanes hook-order crash`) explicitly named the **compute-mode semantics / payload audit** as the remaining deferred Builder follow-up after the crash fix.
- `docs/plans/parseui-current-state-plan.md §5` still names compute-mode semantics / payload verification as the next builder-visible contract audit.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch: `origin/main`
- Current head: `7b33696` — `fix(annotate): prevent TranscriptionLanes hook-order crash (#19)`
- Open implementation PRs against current rebuild `origin/main`: `[]` before this docs handoff PR; current open PR is this docs-only handoff (`#22`)

### Frontend state on current main
- `src/components/parse/RightPanel.tsx`
  - Compare drawer exposes three visible compute modes:
    - `cognates`
    - `similarity`
    - `contact-lexemes`
  - UI currently offers only **Run** + **Refresh** for these modes.
- `src/ParseUI.tsx`
  - `computeMode` defaults to `'cognates'`
  - generic compare compute path is `useComputeJob(computeMode)`
- `src/hooks/useComputeJob.ts`
  - currently calls `startCompute(computeType)` / `pollCompute(computeType, jobId)`
  - **no payload threading** from selected speakers, current concept, or other scope state

### Backend contract on current main
- `python/server.py::_compute_cognates()` accepts richer payload than the drawer currently sends:
  - `threshold`
  - `speakers`
  - `conceptIds`
  - `contactLanguages` / `contact_languages`
  - `annotationsDir`
- `python/server.py` currently routes **both** `cognates` and `similarity` to the same backend function:
  - `normalized_type in {"cognates", "similarity"}` → `_compute_cognates(...)`
  - so today **“similarity” is not a distinct backend operation**
- `python/server.py::_compute_contact_lexemes()` accepts:
  - `providers`
  - `languages`
  - `overwrite`
- `contact-lexemes` already has a dedicated frontend path in `ParseUI` via `crossSpeakerJob`; it is not just another generic `useComputeJob(...)` run

### Existing tests already near this surface
- `src/hooks/__tests__/useComputeJob.test.ts`
- `src/components/parse/RightPanel.test.tsx`
- `src/ParseUI.test.tsx`

## Specific task

1. **Audit the Compare compute drawer end-to-end** and decide the honest semantics for each visible mode.
2. **Implement the smallest clean frontend/shared-shell slice** that matches the current server contract.
3. **Thread explicit payloads** into compare compute runs where the server already supports them.
4. **Resolve the user-facing ambiguity between `cognates` and `similarity`** in a way that is accurate for linguistic analysis.
5. **Add regression tests** for the chosen behavior.

## Required implementation direction

### 1. Make compare compute payloads explicit
At minimum, audit whether compare-mode runs should pass the currently selected speaker subset via `speakers` instead of always falling back to whole-workspace recompute.

Required questions to answer in code + PR notes:
- When multiple speakers are selected in Compare mode, should `cognates` / `similarity` run only on that subset?
- If the drawer has no explicit concept-scope UI, should compute stay whole-workspace for concepts, or should it use a clearly-defined current concept scope?
- If concept scoping is added, it must be **explicit in the UI** and fully tested; do not smuggle in hidden scope changes.

### 2. Keep CLEF on its dedicated path
- Do **not** collapse `contact-lexemes` back into the generic `useComputeJob(...)` path.
- Preserve the current `crossSpeakerJob` + CLEF-config modal flow.
- Do not duplicate the modal’s provider/language controls inside the drawer unless there is a compelling, test-backed reason.

### 3. Fix the semantics mismatch in a user-honest way
Current fact pattern:
- the UI shows separate modes for `cognates` and `similarity`
- the backend currently treats them as the same computation entry point

Your implementation must make that relationship honest. Acceptable outcomes include:
- clearer user-facing copy / status text / test expectations that reflect the shared recompute path, or
- a tighter UI distinction that still maps truthfully onto the current backend behavior

Do **not** leave a misleading UI label that implies a distinct algorithm if the current backend simply rewrites the same enrichments block.

### 4. Preserve data invariants
- Keep concept IDs stable; do not normalize or rewrite them beyond the existing backend contract.
- Do not change the persisted enrichments shape casually.
- Do not introduce silent scope widening that could make comparative results look speaker-filtered when they are not.

## Likely files to touch

Primary expected files:
- `src/ParseUI.tsx`
- `src/hooks/useComputeJob.ts`
- `src/hooks/__tests__/useComputeJob.test.ts`
- `src/components/parse/RightPanel.tsx`
- `src/components/parse/RightPanel.test.tsx`

Possible secondary files:
- `src/api/client.ts`
- `src/api/client.test.ts`

### Boundary rule
Touch `python/server.py` **only if you prove a real contract gap exists** that cannot be handled cleanly in the frontend. If that happens, stop the Builder slice at the boundary and report the exact backend follow-up needed instead of widening this lane casually.

## Validation requirements

Run and report at least:
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- targeted tests for touched compute/parse files
- `git diff --check`

Also do a focused browser smoke in **Compare mode**:
- switch between compute modes
- run the relevant action(s)
- verify progress / error UI remains coherent
- verify any new speaker/concept scoping is reflected honestly in behavior and/or request payload handling

## Academic / fieldwork considerations

- Comparative computation scope matters. A silent whole-workspace recompute when the UI visually suggests a narrowed speaker subset can mislead downstream interpretation.
- “Similarity” language should be conservative and accurate. Historical-linguistic users will infer analytical distinctions from labels.
- Do not trade explicitness for convenience on operations that rewrite `parse-enrichments.json`.

## Out of scope

- new backend algorithms
- NEXUS export work
- annotate-mode refactors unrelated to compare compute
- reopening the resolved `TranscriptionLanes` crash unless your slice directly regresses it

## Reporting requirements

- Open a fresh implementation PR from current `origin/main`.
- In the PR body, explain:
  - what compute semantics were chosen
  - which payloads are now sent (or intentionally not sent)
  - what remains backend-blocked, if anything
- Include exact test commands and results.

## What comes after this task

If you discover a real server-safe follow-up is needed, the next move is **not** to widen this Builder PR. Instead, hand back the exact backend delta so ParseGPT can open a separate parse-back-end handoff PR.