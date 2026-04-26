# parse-builder next queued task — configStore.update frontend parity

## Goal

Implement the still-stubbed `useConfigStore().update()` path so the frontend store finally matches the already-live typed `/api/config` client contract on current `origin/main`, with proper state updates and regression coverage.

## Why this is the right next task now

- Current rebuild `origin/main` is `5cf12ca` (`feat(compare): make compute payload semantics explicit (#24)`).
- Builder is already working the faster frontend cleanup queued in PR #25 (`https://github.com/TarahAssistant/PARSE-rebuild/pull/25`).
- parse-back-end is separately queued on PR #23 (`https://github.com/TarahAssistant/PARSE-rebuild/pull/23`) for backend config/import handler extraction, so this next Builder task should stay **frontend-only** and avoid `python/server.py`.
- On current main, `src/stores/configStore.ts` still has a stale unimplemented stub:
  - `update: async (_patch: Partial<ProjectConfig>) => { ... console.warn("[configStore] update() is not yet implemented"); }`
- That is now inaccurate because:
  - `src/api/client.ts::updateConfig()` already exists
  - backend `PUT /api/config` already exists and is live
- So there is a clean next frontend-parity slice waiting after PR #25.

## Current grounded context

### Repo / PR state
- Repo: `TarahAssistant/PARSE-rebuild`
- Base branch: `origin/main`
- Current head: `5cf12ca`
- Current open PRs:
  - PR #25 — Builder current task: `https://github.com/TarahAssistant/PARSE-rebuild/pull/25`
  - PR #23 — parse-back-end current queued task: `https://github.com/TarahAssistant/PARSE-rebuild/pull/23`

### Relevant current-main files
- `src/stores/configStore.ts`
  - `load()` is implemented
  - `update()` is still a TODO/stub and mentions PATCH even though the typed client uses PUT
- `src/api/client.ts`
  - `updateConfig(patch)` already calls `PUT /api/config`
- `src/__tests__/storePersistence.test.ts`
  - currently covers `configStore.load()` idempotence, but not `update()` behavior
- `src/api/client.test.ts`
  - current tests focus on chat/config schema guards; can be extended only if needed

### Important scoping note
- A repo-wide search shows no current caller of `useConfigStore(...update...)` yet.
- That means this slice is about **restoring store correctness/parity first**, not inventing a new settings UI.
- Do not widen into speculative config-editing UI unless you find an existing dormant surface that already expects this store method.

## Specific task

Implement `configStore.update()` properly and add tests.

### Required implementation direction
1. Replace the stubbed `configStore.update()` implementation with a real call to the existing typed client helper.
2. Keep behavior frontend-only:
   - call `updateConfig(patch)` from `src/api/client.ts`
   - refresh in-memory store state coherently after success
   - surface failure via the store’s `error` field instead of console-only noise
3. Add regression tests for:
   - successful update path
   - error path
   - updated config reflected in store state
4. Remove the stale TODO/warn wording that still claims backend support is missing.

## In scope
- `src/stores/configStore.ts`
- `src/__tests__/storePersistence.test.ts`
- `src/api/client.test.ts` only if a tiny helper-level assertion is useful
- possibly `src/api/client.ts` import surface if needed for testability, but avoid unnecessary churn

## Out of scope
- `python/server.py`
- parse-back-end PR #23’s backend extraction lane
- current Builder PR #25’s BorrowingPanel typed-client cleanup
- new config/settings UI surfaces
- any broad compare/annotate refactor unrelated to config-store parity

## Validation requirements
Run and report at least:
- `npm run test -- --run src/__tests__/storePersistence.test.ts`
- `npm run test -- --run`
- `./node_modules/.bin/tsc --noEmit`
- `git diff --check`

## Academic / UX considerations
- Project config is not decorative; stale or silently unsaved config edits can alter which speakers/concepts/language metadata the workstation exposes.
- The store should fail loudly and deterministically, not emit a warning and pretend the feature exists.
- This task is about making frontend state behavior reproducible and truthful before any future config-editing UI expands.

## Reporting requirements
Open a fresh implementation PR from current `origin/main` **after** the current Builder slice is packaged, unless Lucas explicitly asks for parallel implementation.

In the PR body, include:
- the stale stub removed
- how success updates store state
- how failures surface through the store
- exact tests run

## What comes after this task
If this lands cleanly, Builder can continue frontend contract-hygiene cleanup on other small non-overlapping surfaces without reopening backend work or the already-completed compute-semantics slice.
