# PR #53 stale-task audit

## TL;DR

The implementation requested by https://github.com/TarahAssistant/PARSE-rebuild/pull/53 is **already present on `origin/main`**.

Do **not** open another frontend implementation PR for that bundle. The safe action is to treat PR #53 as stale planning/docs drift.

## What PR #53 asked for

PR #53 queued one frontend-only successor task that would:

1. replace `BorrowingPanel`'s remaining bare CLEF `fetch()` with the typed client path
2. wire `configStore.update()` to the real `updateConfig()` persistence route
3. harden `CognateControls` so failed saves do not silently look successful
4. keep the visible UI unchanged

## Current-state audit against `origin/main`

A fresh branch from current `origin/main` already contains all three requested changes.

### 1) BorrowingPanel already uses the typed CLEF client

`src/components/compare/BorrowingPanel.tsx`
- imports `getClefConfig` from `src/api/client.ts`
- loads CLEF languages through that helper
- no longer performs the bare `/config/sil_contact_languages.json` fetch that PR #53 described as still open

`src/components/compare/BorrowingPanel.test.tsx`
- already mocks `getClefConfig`
- already regression-locks the typed-client path and asserts no bare `fetch()` use

### 2) configStore.update is already wired to typed persistence

`src/stores/configStore.ts`
- already imports `updateConfig`
- already persists patches through the typed client
- already merges successful patches back into local state
- already records the API error on failure

`src/stores/configStore.test.ts`
- already regression-locks successful persistence
- already regression-locks failure behavior

### 3) CognateControls already handles failed saves safely

`src/components/compare/CognateControls.tsx`
- already returns success/failure from `saveGroups()`
- already restores prior grouping state when save fails
- already suppresses `onGroupsChanged` on failure

`src/components/compare/CognateControls.test.tsx`
- already regression-locks the failed-save merge path

## Where this bundle actually landed

These exact frontend contract-hardening changes were already bundled into:

- commit `c5aee8b` — `fix(compare): bundle frontend contract hardening (#34)`

That commit touches exactly the six files that PR #53 describes.

## Practical conclusion

PR #53 should be treated as a stale handoff that was overtaken by already-landed work on `main`.

If a follow-up Builder task is needed after PRs #50 and #52, it should be selected from the **current repo state**, not by replaying PR #53 literally.
