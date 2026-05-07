---
agent: parse-front-end
queued_by: parse-coordinator
queued_at: 2026-05-07T21:20:02Z
status: queued
related_prs:
  - 307
---

# PR #307 follow-up: keep A/B duplicate concept tags in the loaded frontend store

## 1. Goal

Patch **existing PR #307** so duplicating a concept into A/B siblings preserves concept tags both on disk and in the currently loaded React/Zustand annotation state.

PR to update: https://github.com/ArdeleanLucas/PARSE/pull/307

Head branch to update: `fix/duplicate-concept-tag-loss`

Coordinator review comment: https://github.com/ArdeleanLucas/PARSE/pull/307#issuecomment-4401212775

## 2. Why this is the next task now

Coordinator review found PR #307 is directionally correct but **not merge-ready**. The backend copy added in `python/server_routes/exports.py` seeds `concept_tags[siblingId]` from `concept_tags[primaryId]` in annotation JSON files, but the running UI can still hold a stale pre-duplicate annotation record in `useAnnotationStore.records`.

Normal frontend saves post the whole loaded annotation record back to `/api/annotations/{speaker}`. If the loaded record predates the backend sibling-tag copy, the next save/autosave can erase the new sibling tags from disk.

Verified failure sequence from review:

```text
after duplicate:  {'322': ['thesis'], '323': ['thesis']}
after stale save: {'322': ['thesis']}
```

## 3. Grounded context

Fresh coordinator grounding on 2026-05-07:

- PR #307 state: `OPEN`, base `main`, head `fix/duplicate-concept-tag-loss`.
- GitHub state after fetch: `mergeable=MERGEABLE`, `mergeStateStatus=BLOCKED`, `reviewDecision=REVIEW_REQUIRED`.
- CI is green, but review is blocked on this frontend durability gap.
- Changed files currently in PR #307:
  - `python/server_routes/exports.py`
  - `python/test_concept_duplicate_endpoint.py`
  - `src/ParseUI.tsx`

Relevant code paths:

- `src/ParseUI.tsx:1832-1841` currently calls `duplicateConcept(underlyingKey)`, then `reloadConfig()`, then re-resolves the grouped concept by underlying key.
- `src/ParseUI.tsx:2482` now passes `activeRawKey ?? concept.key` into `RightPanel`, which fixes the right-panel lookup key for grouped concepts.
- `src/stores/annotation/persistence.ts:91-99` saves the currently loaded annotation record with `saveAnnotation(speaker, record)` and then replaces store state with the server response.
- `python/server_routes/annotate.py:2989-2994` normalizes the request body and writes it back as the annotation file for the speaker.
- Therefore, this is a **frontend store synchronization problem**, not a backend copy problem.

## 4. Specific task / scope boundary

### In scope

Update PR #307's existing branch, not a new implementation PR:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --quiet --prune
gh pr view 307 --repo ArdeleanLucas/PARSE --json state,headRefName,baseRefName,mergeStateStatus,mergeable,headRefOid,url
# expected headRefName: fix/duplicate-concept-tag-loss

git worktree add --detach /home/lucas/gh/worktrees/front-end-pr307-tag-sync origin/fix/duplicate-concept-tag-loss
cd /home/lucas/gh/worktrees/front-end-pr307-tag-sync
```

Then implement one of these equivalent frontend fixes:

1. **Preferred:** after `duplicateConcept(underlyingKey)` returns `{ primary, sibling }`, patch all currently loaded annotation records in `useAnnotationStore.records`:
   - If `record.concept_tags?.[primary.id]` has tag ids,
   - and `record.concept_tags` does **not** already contain `sibling.id`,
   - set `record.concept_tags[sibling.id] = [...record.concept_tags[primary.id]]`.
   - Preserve existing sibling slots; never overwrite them.
   - Preserve the existing `dirty` state for each speaker. If a record was dirty, it should stay dirty; if it was clean, this sync mirrors the backend disk mutation and does not need to manufacture a user edit.

2. **Acceptable fallback:** force-reload all currently loaded speaker records after duplicate by marking them dirty first so `loadSpeaker()` does not short-circuit. This is less direct and may be heavier, but is acceptable if it is simpler and test-backed.

Keep the fix narrow. A small helper in `src/ParseUI.tsx` or an annotation-store action is fine; choose the least invasive path that keeps the invariant testable.

### Required frontend regression

Add a focused test in `src/ParseUI.test.tsx` that fails on the current PR #307 head and passes after the fix. Suggested shape:

1. Seed config with a concept that can be duplicated, for example primary id `322` / source item `154`.
2. Seed a loaded annotation record for the active speaker with `concept_tags: { "322": ["thesis"] }`.
3. Mock `duplicateConcept()` to return `{ primary: { id: "322", ... }, sibling: { id: "618", ... } }`.
4. Trigger the existing duplicate action through the sidebar context-menu path if practical; otherwise exercise the ParseUI duplicate handler through the same rendered UI path used by existing duplicate tests.
5. Assert the loaded annotation store now includes `concept_tags["618"] === ["thesis"]` while preserving `concept_tags["322"]`.
6. Add a second assertion or test branch for the no-overwrite rule: if `concept_tags["618"]` already exists, it is preserved.

The test should prove in-memory durability, not only right-panel rendering. Right-panel rendering can be an extra assertion, but the blocker is stale full-record save overwriting backend state.

### Out of scope

- Do **not** redesign the duplicate UX.
- Do **not** change backend duplicate semantics unless a frontend test exposes a contract mismatch.
- Do **not** add a new A/B badge, unsplit action, modal, or new dependency.
- Do **not** move PR #307 to a new branch or open a new implementation PR unless PR #307 has already merged/closed. If that happens, stop and report state to parse-coordinator.

## 5. Required validation

Use strict RED/GREEN:

1. On PR #307 head, add the regression first and run it to prove the current failure:

   ```bash
   npx vitest run src/ParseUI.test.tsx
   ```

2. Implement the frontend synchronization fix.

3. Run the focused frontend checks:

   ```bash
   npx vitest run src/ParseUI.test.tsx src/components/parse/right-panel/TagsPanelSection.test.tsx
   ./node_modules/.bin/tsc --noEmit
   git diff --check
   ```

4. Because PR #307 also contains backend changes, keep the existing backend duplicate endpoint evidence fresh:

   ```bash
   PYTHONPATH=python python3 -m pytest -q python/test_concept_duplicate_endpoint.py
   uvx ruff check python/server_routes/exports.py python/test_concept_duplicate_endpoint.py --select E9,F63,F7,F82
   ```

5. If the focused frontend run passes quickly, run the full frontend gate before final push:

   ```bash
   npx vitest run
   ./node_modules/.bin/tsc --noEmit
   npm run build
   ```

6. Push back to the existing PR branch and verify fresh status:

   ```bash
   git push origin HEAD:fix/duplicate-concept-tag-loss
   git fetch origin --quiet --prune
   gh pr view 307 --repo ArdeleanLucas/PARSE --json mergeable,mergeStateStatus,reviewDecision,headRefOid,statusCheckRollup,url
   ```

Post a concise evidence comment on PR #307 naming the new test and validation results.

## 6. What comes after this task

After parse-front-end updates PR #307:

1. parse-coordinator re-reviews PR #307.
2. If the stale-save durability test passes and CI stays green, coordinator can approve/sign off.
3. Lucas/TrueNorth49 can merge PR #307.
4. The older broad handoff `.hermes/handoffs/parse-front-end/2026-05-07-concept-duplicate-ui.md` can be considered superseded/completed by the duplicate UI work plus this PR #307 follow-up; do not start a second duplicate-UI lane from it.

## Reply expected from parse-front-end

Reply on PR #307 and to Lucas with:

- PR URL: https://github.com/ArdeleanLucas/PARSE/pull/307
- Commit SHA pushed to `fix/duplicate-concept-tag-loss`
- The exact regression test name added
- Validation commands and pass counts
- Fresh `mergeable` / `mergeStateStatus` after `git fetch origin --quiet --prune`
