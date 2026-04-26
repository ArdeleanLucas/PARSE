---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
authorized_by: lucas
related_prs:
  - 19  (rebuild TranscriptionLanes hook-order fix)
  - 77  (rebuild path-separator fix MC-323)
  - 230 (oracle TranscriptionLanes hook-order issue)
  - 231 (oracle path-separator issue)
  - 232 (oracle path-separator issue, related)
  - 96  (coordinator sync where Lucas authorized this)
related_skills:
  - parse-mc-workflow
  - parse-pr-workflow
  - github-pr-workflow
---

# parse-gpt task — oracle sync PRs (LIVE-RUNTIME-FIX, AUTHORIZED)

**Why this exists:** Lucas authorized 2026-04-26 (in PR #96 sync doc decisions): sync the path-separator fix (#77) and TranscriptionLanes hook-order fix (#19) from rebuild to oracle. Per AGENTS.md exception case, live thesis-runtime bug fixes require explicit per-task approval — this handoff IS the explicit approval.

## Working environment

**This task uniquely requires writing to the oracle repo (`ArdeleanLucas/PARSE`).** Per AGENTS.md exception case for "live thesis-runtime bug fix that Lucas explicitly requests" — both PRs below qualify and have approval.

For these PRs only:

- Working clone: `/home/lucas/gh/ardeleanlucas/parse` (oracle clone)
- Verify before pushing: `git remote -v` shows `ArdeleanLucas/PARSE`
- `gh pr create --repo ArdeleanLucas/PARSE --base main ...` (note: oracle repo, not rebuild)
- PR title prefix: `fix(live):` per AGENTS.md convention
- Reference: links to rebuild PRs #19 / #77 / #96 + oracle issues #230 / #231 / #232

For all OTHER work, the standard rule still applies: rebuild repo only.

## Task A — Sync path-separator fix to oracle

**What to do**: cherry-pick the one-line fix from rebuild PR #77 (MC-323) onto a new branch in the oracle clone, open as PR on `ArdeleanLucas/PARSE`.

**Procedure:**

```
$ cd /home/lucas/gh/ardeleanlucas/parse
$ git fetch origin main --quiet
$ git remote add rebuild git@github.com:TarahAssistant/PARSE-rebuild.git 2>/dev/null || true
$ git fetch rebuild fix/mc-323-display-readable-path-posix --quiet
$ git checkout -B fix/sync-path-separator-from-rebuild-77 origin/main
$ git cherry-pick <SHA of #77's commit on rebuild>
# Cherry-pick should apply cleanly — chat_tools.py:_display_readable_path
# is byte-identical between oracle and rebuild at this location (the bug
# was carried into the rebuild from oracle, so the fix syncs back).
$ python3 -m pytest python/test_chat_tools_*.py python/test_import_processed_speaker_*.py -v
$ git push -u origin HEAD
$ gh pr create --repo ArdeleanLucas/PARSE --base main \
    --title "fix(live): sync path-separator fix from rebuild PR #77 (MC-323)" \
    --body "<see body template below>"
```

**PR body template:**

```
## Summary

Syncs the one-line fix from rebuild PR #77 (MC-323) to oracle.

**Bug**: `python/ai/chat_tools.py:_display_readable_path` was using `str(path.relative_to(self.project_root))`, which returns Windows backslashes on Windows. The result was being persisted to disk in `source_index.json` and `annotation.source_audio`, breaking cross-platform workspace portability.

**Fix**: one-line change to `path.relative_to(self.project_root).as_posix()` — always returns POSIX forward slashes regardless of OS.

## Origin

- Rebuild PR: TarahAssistant/PARSE-rebuild#77 (MC-323)
- Oracle issues addressed: #231, #232
- Discovery: parse-back-end's PR #72 backend test failure audit on rebuild

## Test plan

- [ ] `python3 -m pytest python/test_import_processed_speaker_*.py` passes (the 2 real-bug tests should now pass on oracle just as they do on rebuild)
- [ ] No new test failures
- [ ] Manual verification: import a processed speaker on Windows + read source_index.json and verify forward slashes

## Why now

Authorized by Lucas 2026-04-26 during coordinator sync (rebuild PR #96).
```

**Acceptance:**
- One-line change at `python/ai/chat_tools.py:_display_readable_path`
- Existing tests pass (the 2 previously-failing import_processed_speaker tests should now pass on oracle)
- Closes oracle issues #231 and #232 when merged

## Task B — Sync TranscriptionLanes hook-order fix to oracle

**What to do**: cherry-pick the fix from rebuild PR #19 (`fix(annotate): prevent TranscriptionLanes hook-order crash`) onto a new branch in the oracle clone, open as PR on `ArdeleanLucas/PARSE`.

**Why it matters**: the bug crashes the `/annotate` route on Lucas's Saha01 fixture (verified during PR #66 Annotate parity pass). Lucas's live thesis runtime is currently broken on this flow.

**Procedure:** same shape as Task A:

```
$ cd /home/lucas/gh/ardeleanlucas/parse
$ git fetch origin main --quiet
$ git fetch rebuild fix/annotate-transcription-lanes-hook-order-crash --quiet
$ git checkout -B fix/sync-transcription-lanes-hook-order-from-rebuild-19 origin/main
$ git cherry-pick <SHA of #19's commit on rebuild>
$ npm install   # if needed for oracle's node_modules
$ npm run typecheck && npm run test -- --run src/components/annotate/TranscriptionLanes
$ git push -u origin HEAD
$ gh pr create --repo ArdeleanLucas/PARSE --base main \
    --title "fix(live): sync TranscriptionLanes hook-order fix from rebuild PR #19" \
    --body "<see body template below>"
```

**PR body template:**

```
## Summary

Syncs the React hook-order fix from rebuild PR #19 to oracle.

**Bug**: `src/components/annotate/TranscriptionLanes.tsx` had hooks called in non-stable order between renders, causing React to throw "Rendered more hooks than during the previous render." This crashes the `/annotate` route when entering Annotate mode on the Saha01 fixture (and likely other speaker workspaces with specific lane-state combinations).

**Fix**: per rebuild PR #19's commit — moves hook calls to top-level, ensures consistent hook order regardless of conditional render branches.

## Origin

- Rebuild PR: TarahAssistant/PARSE-rebuild#19
- Oracle issue addressed: #230
- Discovery: rebuild PR #66 Annotate parity pass — recorded oracle's crash as a "deviation" while rebuild loaded successfully

## Test plan

- [ ] `npm run typecheck` passes
- [ ] `npm run test -- --run src/components/annotate/TranscriptionLanes` passes
- [ ] Manual verification: open `/annotate` on Saha01 fixture, verify it loads (not ErrorBoundary) and waveform appears

## Why now

Authorized by Lucas 2026-04-26 during coordinator sync (rebuild PR #96). Lucas's live thesis annotate workflow is currently broken on this fixture; this fix restores it.
```

**Acceptance:**
- Cherry-pick from rebuild #19 applies cleanly (file should be byte-identical to oracle except for the fix region)
- TranscriptionLanes test passes
- Manual `/annotate` smoke test on Saha01 fixture loads without ErrorBoundary
- Closes oracle issue #230 when merged

## Order

Task A first (mechanically simpler, smaller surface), then Task B (touches React rendering — verify with browser smoke). Either order is acceptable; both are independent.

## Out of scope

- Any other rebuild → oracle sync work — this handoff covers exactly these two fixes
- Touching `desktop/` or other Option 3 surfaces (cancelled per PR #95 / coordinator sync)
- Coordinator work like merge tail draining, parity passes — separate handoff PR #92 covers that

## Conventions

- One commit per cherry-pick (don't bundle into a single PR — they're independent fixes)
- PR title prefix: `fix(live):` (oracle convention; rebuild uses `fix(scope):`)
- Co-author line: `Co-Authored-By: parse-gpt <noreply@anthropic.com>`
- Do not merge your own PRs — Lucas reviews and merges oracle PRs himself

## After PRs land

- Update rebuild PR #66 (Annotate parity evidence) with a follow-up note: oracle hook-order crash is now fixed via oracle sync PR; future Annotate parity passes against oracle should not encounter this deviation
- Update `docs/plans/option1-parity-inventory.md` §11 (Accepted oracle deviations) — mark the two synced bugs as RESOLVED with sync PR links
- Close the loop on oracle issues #230, #231, #232 once their respective oracle PRs merge (Lucas merges, you follow up to close)
