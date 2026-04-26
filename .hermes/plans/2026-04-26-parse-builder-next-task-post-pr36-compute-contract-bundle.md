# parse-builder next task — post-PR36 compute contract bundle

## Goal

Ship **one fresh frontend-only Builder implementation PR** from the latest `origin/main` _after finishing PR #36_ that audits, fixes, and regression-locks the **active ParseUI compare-compute contract**.

This is not a UI redesign task. Keep the visible React workstation behavior aligned with the current PARSE shell; make the semantics explicit, typed, and test-backed.

## Why this is the right next task now

- **PR #36** is already the queued Builder lane for the Decisions import/export contract.
- **PR #41** owns the `RegionManager` annotate parity slice.
- **PR #43** owns the annotate offset-shell regression slice.
- **PR #42** and **PR #44** are parse-back-end lanes.

So the next real Builder-owned gap must be **post-PR36**, frontend-only, and outside annotate/backend overlap.

The live execution plan points directly at this:
- `docs/plans/parseui-current-state-plan.md`
- §4 = decisions story (owned by PR #36)
- **§5 = verify compute-mode semantics against the server**

That makes the next grounded active-shell slice the compare compute contract in:
- `src/ParseUI.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/hooks/useComputeJob.ts`
- related tests

## Current grounded evidence

### 1. The live plan still marks compute semantics as open
`docs/plans/parseui-current-state-plan.md` explicitly says the remaining work is to verify:
- each selected `computeMode` maps to a real supported server compute type
- whether any extra payload is needed
- whether **Refresh** means reload enrichments only or re-run compute

### 2. The active shell now has substantial compute wiring, but the contract is mostly encoded in comments rather than regression tests
In `src/ParseUI.tsx` today:
- `computeMode` lives as local state initialized to `'cognates'`
- non-CLEF modes route through `useComputeJob(computeMode)`
- `contact-lexemes` routes through the dedicated `crossSpeakerJob`
- successful CLEF populate can auto-chain a `similarity` compute
- `listActiveJobs()` rehydrates contact-lexemes/similarity jobs on mount

That is good functionality, but it is a high-risk contract area with limited focused coverage.

### 3. `RightPanel` compute behavior is under-tested
`src/components/parse/RightPanel.test.tsx` currently covers speaker-selection behavior only.
It does **not** lock down the compare compute controls for:
- compute-mode switching
- Run button dispatch expectations
- Refresh semantics
- CLEF Configure / Sources Report affordances
- disabled-state behavior while jobs are running
- non-contact running/error indicator behavior

### 4. Type looseness still obscures the contract
`src/components/parse/RightPanel.tsx` currently uses:
- `type ComputeMode = 'cognates' | 'similarity' | 'contact-lexemes' | string`
- `type JobStatus = 'idle' | 'running' | 'complete' | 'error' | string`

Those `| string` escape hatches make it easier for UI/server drift to sneak in silently.

## Source of truth

Primary active-shell sources:
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/components/parse/RightPanel.test.tsx`
- `src/hooks/useComputeJob.ts`
- `src/hooks/__tests__/useComputeJob.test.ts`
- `src/api/client.ts`
- `python/server.py`
- `python/workers/compute_worker.py`
- `docs/plans/parseui-current-state-plan.md`
- `AGENTS.md`

UI/oracle constraint:
- No re-imagining. Preserve the current PARSE workstation UI shape.

## Specific task

Create **one fresh Builder implementation PR** from the latest `origin/main` that hardens the active compare-compute contract.

### Required implementation direction

1. **Audit and make compute-mode semantics explicit in the active shell.**
   - Confirm the three visible compare modes map cleanly to server-supported compute types:
     - `cognates`
     - `similarity`
     - `contact-lexemes`
   - If the current mapping is already right, keep behavior and encode it in types/tests.
   - If there is any real drift, patch it minimally without redesigning the UI.

2. **Tighten the type surface.**
   - Remove unnecessary `| string` escape hatches around compute mode / job status where safe.
   - Prefer a shared or clearly-local explicit union over silently-open strings.
   - Keep TypeScript strict-clean.

3. **Regression-lock `RightPanel` compare compute behavior.**
   Add/expand tests so they prove:
   - mode switching is wired
   - clicking **Run** calls the provided handler
   - **Refresh** means reload-enrichments only unless the audited contract proves otherwise
   - `contact-lexemes` mode shows CLEF status row and Configure / Sources Report controls
   - contact-lexemes Run button disables off `crossSpeakerJobStatus`
   - non-contact modes disable off `computeJobStatus`
   - running/error text appears only for non-contact compute modes as intended

4. **Regression-lock `ParseUI`'s contact-lexemes/similarity orchestration.**
   Add focused tests for the active shell contract, especially:
   - if CLEF is not configured, compare-drawer Run opens config instead of starting the job
   - if CLEF is configured, `contact-lexemes` Run goes through `crossSpeakerJob`
   - a successful populate with `total_filled > 0` auto-chains similarity recompute
   - a successful populate with `0` filled forms does **not** auto-chain similarity
   - `listActiveJobs()` rehydrates in-flight `contact-lexemes` / `similarity` jobs on mount
   - Refresh semantics stay intentional and explicit

5. **Touch production code only where the audit proves it is needed.**
   This can legitimately end up as mostly tests + type hardening if the runtime wiring is already correct.
   If a real bug emerges during the audit, fix it in the same PR.

## In scope

- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/parse/RightPanel.tsx`
- `src/components/parse/RightPanel.test.tsx`
- `src/hooks/useComputeJob.ts`
- `src/hooks/__tests__/useComputeJob.test.ts`
- narrowly related shared types/helpers if justified

## Out of scope

- PR #36 decisions-contract work
- annotate-mode parity work owned by PRs #41 / #43
- parse-back-end lanes PR #42 / #44
- legacy compare-only components unless a tiny shared helper change truly requires it
- UI redesign / copy refresh for the compute drawer

## Validation requirements

Run and report at least:
- targeted tests you add/update for ParseUI / RightPanel / useComputeJob
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`
- browser smoke of compare-mode compute controls if production code changes

## Reporting requirements

Open **one fresh Builder implementation PR** from the latest `origin/main`.

In the PR body include:
- which compute semantics were confirmed vs changed
- whether Refresh remained a reload-only action or required adjustment
- any production-code changes vs test-only/type-only hardening
- confirmation of non-overlap with PRs #36, #41, #43, #42, and #44
- exact tests run

## Academic / fieldwork considerations

- Comparative compute actions directly affect cognate adjudication and contact-lexeme evidence surfaces.
- Silent compute-mode drift is dangerous because it can make the UI appear scientifically coherent while actually dispatching the wrong backend job or stale enrichments.
- This task improves reproducibility by making the active compare-compute contract explicit, test-backed, and easier to audit.