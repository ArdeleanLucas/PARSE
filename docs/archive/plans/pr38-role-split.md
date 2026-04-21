# PR #38 Role Split — Opus (planner) vs parse-gpt (coder)

> **Archived historical coordination note (2026-04-21):** this file describes the agent split for one completed PR-era slice. Do not reuse it as a live operating procedure. Current PARSE workflow, branch policy, and validation gates live in `AGENTS.md`.

**PR:** #38 `feat/actions-job-lifecycle`
**Branch:** `feat/actions-job-lifecycle` from `origin/main`

---

## Roles

| Role | Agent | Tools | Strengths |
|---|---|---|---|
| **Opus** (ParseBuilder) | This session — planner/architect | Full OpenClaw toolset, browser, memory, cross-repo context | Architecture decisions, contract audits, test specs, PR docs, review, coordination |
| **parse-gpt** | OpenCode coding sub-agent | File read/write in `/home/lucas/.openclaw/workspace/parse/`, terminal | Focused code generation, TDD cycles, file-scoped implementation |

**Handoff protocol:** Opus writes a task brief per dispatch → `opencode_task` sends it to parse-gpt → parse-gpt codes on `feat/actions-job-lifecycle` → Opus reviews the diff, runs tests, adjusts.

---

## Phase 1 — Opus does (before any code)

### 1A. Write the `useActionJob` hook spec

Opus produces the **exact TypeScript interface, parameter contract, and behavior rules** that parse-gpt implements. This is the brain work — getting the generic abstraction right so it fits normalize, STT, and compute without special-casing.

**Deliverable:** A task brief with:
- Full `useActionJob` type signature (input config + return shape)
- State machine rules: idle → running → complete | error
- Polling semantics: interval, guard against concurrent polls, cleanup on unmount
- Progress normalization rules (0–100 → 0–1)
- `onComplete` / `onError` callback contract
- How `reset()` works

### 1B. Write the test spec for `useActionJob`

Opus defines the **test cases** (RED phase). parse-gpt writes the test file and implementation.

**Test cases to specify:**
1. Starts idle, transitions to running on `run()`
2. Polls and transitions to complete when server returns `done`/`complete`
3. Polls and transitions to error when server returns `error`/`failed`
4. Fires `onComplete` callback on success
5. Normalizes progress > 1 (e.g. 68 → 0.68)
6. Cleanup on unmount cancels interval
7. Double `run()` call doesn't stack two polling loops
8. `reset()` returns to idle and clears error

### 1C. Define the per-action wiring table

Opus maps each action button → exact client function → exact poll function → exact onComplete side-effect. parse-gpt shouldn't have to figure out which API calls to use.

| Action button | `start` call | `poll` call | `onComplete` |
|---|---|---|---|
| Run Audio Normalization | `startNormalize(speaker)` | `pollNormalize(jobId)` | `annotationStore.load(speaker)` |
| Run Orthographic STT | `startSTT(speaker, \`${speaker}.wav\`, 'ckb')` | `pollSTT(jobId)` | `annotationStore.load(speaker)` |
| Run IPA Transcription | `startCompute('ipa_only')` | `pollCompute('ipa_only', jobId)` | `enrichmentStore.load()` |
| Run Full Pipeline | `startCompute('full_pipeline')` | `pollCompute('full_pipeline', jobId)` | `enrichmentStore.load()` |
| Run Cross-Speaker Match | `startCompute('contact-lexemes')` | `pollCompute('contact-lexemes', jobId)` | `enrichmentStore.load()` |

### 1D. Design the status indicator UI spec

Opus decides the **layout and states** for the topbar status indicator. parse-gpt builds it.

**Spec:**
- Position: below the Actions dropdown, inside TopBar
- Idle: hidden
- Running: `"{label}… ████░░░░ {pct}%"` with Tailwind progress bar
- Complete: `"✓ {label} done"` — auto-dismiss after 3s
- Error: `"✗ {label} failed: {msg}"` + Dismiss button
- Multiple jobs: stack vertically

---

## Phase 2 — parse-gpt dispatches (Opus sends via `opencode_task`)

### Dispatch 1: `useActionJob` hook + tests

**Task brief for parse-gpt:**
> Working on branch `feat/actions-job-lifecycle` in `/home/lucas/.openclaw/workspace/parse/`.
>
> Create `src/hooks/useActionJob.ts` implementing [the spec from 1A].
> Create `src/hooks/__tests__/useActionJob.test.ts` with [the test cases from 1B].
>
> Run `npm run test -- src/hooks/__tests__/useActionJob.test.ts --run` and `npm run check` before finishing.
> Do NOT modify any other files.

**Opus reviews:** Check diff, run full suite, verify the hook API matches the spec.

### Dispatch 2: Refactor `useComputeJob` → wrapper

**Task brief for parse-gpt:**
> Working on branch `feat/actions-job-lifecycle`.
>
> Refactor `src/hooks/useComputeJob.ts` to be a thin wrapper around `useActionJob`.
> Import `useActionJob` from `./useActionJob`.
> Preserve the exact same return type `{ start, state }` and `ComputeJobState` export.
> Do NOT change `src/hooks/__tests__/useComputeJob.test.ts` — existing tests must pass as-is.
>
> Run `npm run test -- src/hooks/__tests__/useComputeJob.test.ts --run` and `npm run check`.

**Opus reviews:** Confirm existing `useComputeJob` tests pass without modification. This proves the refactor is safe.

### Dispatch 3: Wire Actions menu + status indicator

**Task brief for parse-gpt:**
> Working on branch `feat/actions-job-lifecycle`.
>
> In `src/ParseUI.tsx`, in the `TopBar` component:
>
> 1. Add 5 `useActionJob` instances using [the wiring table from 1C].
> 2. Replace the 5 fire-and-forget `onClick` handlers with `{job}.run`.
> 3. Add `disabled={{job}.state.status === 'running'}` to each button.
> 4. Update button labels to show "{label}…" while running.
> 5. Add an `ActionStatusBar` section below the Actions dropdown [per UI spec from 1D].
> 6. In the Reset Project handler, call `.reset()` on all 5 action jobs.
>
> Do NOT modify `src/api/client.ts`, `src/api/types.ts`, `python/server.py`, or anything in `src/components/compare/`.
>
> Run `npm run test -- --run` and `npm run check`.

**Opus reviews:** Full test suite, typecheck, visual review of the diff for correct hook wiring.

### Dispatch 4: ParseUI regression tests

**Task brief for parse-gpt:**
> Working on branch `feat/actions-job-lifecycle`.
>
> In `src/ParseUI.test.tsx`, add regression tests for:
> 1. Actions menu renders all 5 processing action buttons
> 2. Clicking "Run Audio Normalization" changes button text to "Normalizing…"
> 3. Action buttons are disabled while their job state is 'running'
> 4. Reset Project clears action states
>
> Use existing test patterns from `src/ParseUI.test.tsx` (mock stores, render ParseUI, query by role/text).
>
> Run `npm run test -- --run` and `npm run check`.

**Opus reviews:** Verify test assertions are meaningful, not just "it renders."

---

## Phase 3 — Opus does (after code lands)

### 3A. Full test suite + typecheck gate
```bash
npm run test -- --run    # must be >= 119 (expect ~127+)
npm run check            # clean
```

### 3B. Review the complete diff
- No raw `fetch()` in ParseUI action handlers
- No `console.error` as the only error path
- `useComputeJob` tests unchanged
- No changes to `client.ts`, `types.ts`, `server.py`, or compare components

### 3C. Commit, push, update PR #38
- Squash or keep meaningful commits
- Update PR description with final test count
- Ping TrueNorth49 for review

### 3D. Update docs
- Update `docs/plans/parseui-current-state-plan.md` §3 to mark Actions job lifecycle as done
- Update `AGENTS.md` test floor if it increased

---

## Summary

| Phase | Who | What | # dispatches |
|---|---|---|---|
| **1 — Spec** | Opus | Hook interface, test spec, wiring table, UI spec | 0 |
| **2 — Code** | parse-gpt | Hook, refactor, wiring, regression tests | 4 sequential |
| **3 — Review** | Opus | Gate, review, push, update docs | 0 |

**Opus owns:** architecture decisions, API mapping, test case design, review, PR management
**parse-gpt owns:** writing the TypeScript, running the tests, staying in file scope
