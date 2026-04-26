# ParseBuilder next task — fix the Compare → Annotate `TranscriptionLanes` hook-order crash

**Repo:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
**Date:** 2026-04-26
**Owner:** parse-builder
**Status:** queued / ready on current `origin/main`
**Replaces stale handoff PRs:** PR #5 and PR #16

## Goal

Open a fresh Builder PR from current rebuild `origin/main` that fixes the pre-existing Annotate-mode crash triggered when switching Compare → Annotate, where React throws:

> `Rendered more hooks than during the previous render`

The working hypothesis from current rebuild state is that the failure is in or adjacent to the `TranscriptionLanes` subtree. This task is to reproduce it, isolate the root cause, add a regression test, implement the smallest correct fix, and ship it as a frontend-only bugfix PR.

---

## Why this is the right next Builder task

The two earlier builder handoff PRs are no longer safe execution guides:
- PR #5 is old Stage-1 guidance and was already superseded by landed shell work
- PR #16 was closed because it described PR topology incorrectly once rebuild state moved forward

Current live state is:
- PR #14 remains the active Builder implementation PR for decisions persistence
- PR #13 is no longer open; it is already merged into `main`
- the current Builder automation state still records the Compare → Annotate `TranscriptionLanes` hook-order crash as the main unresolved frontend blocker

Because Lucas asked for the next Builder task now, the safe resequencing is:
1. leave PR #14 separate
2. do not widen PR #14
3. open a fresh Builder bugfix PR for the hook-order crash
4. return to the deferred compute-mode semantics audit only after this browser blocker is removed

This remains the best parallel Builder task because it stays frontend-owned and does not depend on the already-merged backend auth slice.

---

## Current grounded context

Verified from current rebuild state before writing this prompt:

- Current rebuild `origin/main` tip:
  - `4ed1eb7` (`refactor: extract auth HTTP handlers (#13)`)
- Active Builder implementation PR:
  - PR #14 — `feat: unify decisions persistence flows`
  - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/14`
  - head: `auto/parse-builder`
  - note in PR body: Annotate browser smoke still had the pre-existing `TranscriptionLanes` hook-order crash and it was intentionally left out of that slice
- Current Builder automation state:
  - open PR recorded there: PR #14
  - blocker recorded there: Compare → Annotate `TranscriptionLanes` hook-order crash
- parse-back-end auth slice:
  - PR #13 — merged
  - merge commit: `4ed1eb7`
- parse-gpt coordination PR:
  - PR #15 — `docs: add three-lane health coordination note`
  - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/15`
- Stale Builder handoff PRs that should no longer be used as the task source:
  - PR #5 — `https://github.com/TarahAssistant/PARSE-rebuild/pull/5`
  - PR #16 — `https://github.com/TarahAssistant/PARSE-rebuild/pull/16` (closed as stale)

Frontend surfaces likely relevant:
- `src/ParseUI.tsx`
- `src/components/annotate/TranscriptionLanes.tsx`
- `src/stores/transcriptionLanesStore.ts`
- any small annotate hook/helper directly involved in lane rendering or conditional hook execution

---

## The specific task

Fix the hook-order crash that occurs when the user transitions from Compare mode into Annotate mode.

### Required outcome

After the fix:
- Compare → Annotate navigation must no longer throw a React hook-order error
- Annotate mode must render successfully after the transition
- the relevant lane UI must still behave correctly
- the fix must be covered by regression tests

### Strong recommendation

Treat this as a bugfix/root-cause task, not a speculative refactor.

That means:
1. reproduce it first
2. isolate the exact conditional hook-order violation
3. add a failing test that captures the transition
4. apply the smallest root-cause fix
5. rerun the full frontend gates

---

## Scope boundary

### In scope
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/components/annotate/TranscriptionLanes.tsx`
- `src/components/annotate/TranscriptionLanes*.test.tsx` if needed
- `src/stores/transcriptionLanesStore.ts` if the root cause genuinely lives there
- a very small helper/hook extraction only if necessary to make hook order deterministic

### Read-only unless the bug proves otherwise
- `python/**`
- `src/api/client.ts`
- `src/api/types.ts`
- `src/components/compare/**`
- `src/components/compute/**`
- `src/components/shared/**`
- PR #14 files unrelated to the crash

### Explicitly out of scope
- finishing compute-mode semantics audit
- backend route or payload changes
- decisions persistence redesign
- broad ParseUI decomposition beyond what is strictly required for the hook-order bug

---

## Reproduction target

Use the actual user-visible flow as the acceptance path:
1. load the app
2. enter Compare mode
3. switch into Annotate mode
4. confirm the previous React hook-order crash no longer occurs

If the browser reproducer depends on specific state or speaker selection, document the exact minimum reproducer in the PR body and lock it into tests.

---

## Testing requirements

### Required TDD sequence
1. add or strengthen a regression test that fails before the fix
2. implement the fix
3. re-run targeted tests
4. re-run the full frontend gates

### Minimum required test coverage
- a regression test for Compare → Annotate transition that would previously trip the hook-order crash
- direct component coverage for the specific lane/render condition that caused the hook mismatch, if isolatable
- preservation of existing Annotate render behavior after the fix

### Required validation commands
```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
git diff --check
```

### Recommended targeted commands
```bash
npm run test -- --run src/ParseUI.test.tsx
npm run test -- --run src/components/annotate/TranscriptionLanes.test.tsx
```

If the final targeted test file names differ, run the equivalent focused suites and name them in the PR body.

---

## Branch / PR guidance

Use a fresh branch from rebuild `origin/main`.

Recommended branch name:

```text
fix/annotate-transcription-lanes-hook-order-crash
```

Do not reopen or mutate PR #5.
Do not reopen PR #16.
Do not silently expand PR #14.
Ship this as a separate Builder bugfix PR.

---

## Reporting requirements

In the final Builder report, include:
1. PR number + URL
2. worktree path used
3. exact root cause found
4. files changed
5. tests added
6. validation results
7. explicit statement that PR #14 was left separate

---

## What should come after this

If this crash fix lands cleanly, the next Builder-visible slice after that can return to the deferred plan item previously recorded in `parse-builder.json`:
- `docs/plans/parseui-current-state-plan.md` §5
- compute-mode semantics / payload audit

But that is **not** this task. This task is to remove the current Annotate-mode browser blocker first.
