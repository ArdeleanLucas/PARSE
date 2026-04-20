# MC-300 — ParseUI unified shell recovery + Priority 1 wiring

> **Historical note:** this recovery task belongs to the earlier rolling-branch period. The branch names below are historical references; current work now branches from `origin/main`.

## Objective
Recover the ParseUI unified shell after the broken wiring attempt, then complete the thesis-critical Priority 1 wiring tasks from `docs/plans/parseui-wiring-todo.md` in a test-backed way.

## Scope
1. Verify branch state against current PARSE policy:
   - code/docs branches now start from `origin/main`
   - the old `feat/parseui-unified-shell` and `docs/parseui-planning` lanes are historical/deleted
2. Restore `src/ParseUI.tsx` so the app imports and builds again.
3. Re-run targeted ParseUI tests to confirm RED/GREEN state.
4. Complete Priority 1 tasks sequentially:
   - stale concept/speaker refs
   - annotation prefill from store
   - save annotation wiring
   - mark done wiring
   - reactive missing/annotated badge
   - stale comment cleanup
5. Run `npm run check` after each completed task slice, then targeted/full tests.

## Known facts
- Current repo path: `/home/lucas/gh/ardeleanlucas/parse`
- MC board highest number before this task: MC-299
- `src/ParseUI.tsx` was reported missing during the prior run and must be recovered before more wiring.
- User requires MC tasks to be created/updated throughout the workflow and checked off when done.

## Files likely involved
- `src/ParseUI.tsx`
- `src/ParseUI.test.tsx`
- `src/stores/annotationStore.ts`
- possibly `src/App.tsx` only for validation, not planned edits

## Completion criteria
- `src/ParseUI.tsx` restored and importable
- Priority 1 wiring implemented cleanly
- `npm run check` passes
- targeted ParseUI tests pass
- MC-300 updated with results and checked off when complete
