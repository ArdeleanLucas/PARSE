---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - none — pick up immediately, no prerequisites
related_skills:
  - parse-rebuild-three-lane-pr-coordination
  - parse-rebuild-progress-scorecard
  - parse-rebuild-annotate-parity-audit
  - parse-mc-workflow
---

# parse-gpt next task — finish merge wave, file path-separator bugs, run Compare parity

**Why this exists:** Last burst (5 merges + oracle #230 + PR #64 classification) was excellent. Four discrete next tasks remain, in the priority order below. None are large; all are unblockers for downstream work.

## Working environment

Same rule as everywhere else. Verify before any push:

```
$ pwd
/home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT
$ git remote -v
origin  git@github.com:TarahAssistant/PARSE-rebuild.git (fetch)
$ gh pr create --repo TarahAssistant/PARSE-rebuild --base main ...   # --repo mandatory
```

If you see `ArdeleanLucas/PARSE`, switch clones before continuing. See PR #74 (just opened) for the strengthened AGENTS.md repo-target rule.

## Task 1 — Finish PR #65 scorecard refresh and push

You started the post-merge update but didn't commit/push before tool budget ran out. Pick it up:

- Rebuild SHA: refresh from `4ffb31dd6f` to current `origin/main` at the moment of writing
- Monolith table: update ParseUI.tsx row to **3537 LoC** (down from 4404 at queue time, down from 5328 oracle baseline). Update other rows if the merge wave has touched them.
- 24h merge stats: refresh to current count (was 39 at last update)
- Open PR snapshot: list the current 11+ open PRs with one-line status each. Group by lane.
- Interpretation text: note that the rebuild parity baseline is now red-but-classified per PR #64's update — parity claims now have known caveats rather than unknown caveats.

Commit + push to PR #65. Should not be more than 30 minutes of work since the structure is already drafted.

## Task 2 — File 2 follow-up oracle issues for the real-bug failures

PR #64's classification table identified two **real-bug** failures shared between oracle and rebuild:

- `test_import_processed_speaker_write_copies_assets_and_builds_workspace_files`
- `test_import_processed_speaker_preserves_existing_sources_and_clears_stale_optional_metadata`

Root cause per your audit: *"persisted project metadata is leaking Windows path separators into source_index.json"*.

File these as one or two issues on `ArdeleanLucas/PARSE` (oracle, since it's a shared bug — the live thesis runtime needs the fix as much as rebuild does):

- Title suggestion (single issue): `bug: source_index.json leaks Windows path separators in import-processed-speaker write path`
- Reference both failing test names + traceback excerpts from PR #64's classification
- Note that the bug is shared with rebuild repo (test failures present in both)
- Do NOT fix the bug yourself — filing only. Implementation is whoever picks up the issue.

Same one-shot pattern you used for issue #230. After filing, link back from PR #64's classification table.

## Task 3 — Continue the merge wave

7 PRs ahead of you. Suggested order (verify dependencies before following blindly):

**Implementation lane:**

1. **#68** `refactor(chat_tools): extract read-only chat tool bundles` — parse-back-end's PR 1 cherry-pick. Should merge cleanly, no conflicts (rebuild's chat_tools.py is byte-identical to oracle's pre-extraction state).
2. **#69** `refactor(parseui): extract AnnotateView from ParseUI.tsx` — parse-builder Step 3. May need rebase since #61/#62/#63 already landed and rewrote chunks of ParseUI.tsx; quick conflict-resolve at most.
3. **#71** `refactor(parseui): lift reference-form parsing utilities` — parse-builder follow-on PR B from handoff #70. Likely clean rebase; pure-function lift.
4. **#73** `refactor(parseui): extract annotate helpers` — parse-builder follow-on PR A from handoff #70. May conflict with #69 if both land before rebase; if so, rebase #73 onto #69's merge.

**Handoffs:**

5. **#70** `handoff(parse-builder): close ParseUI.tsx ≤1800 LoC gap` — docs-only, merge whenever
6. **#72** `handoff(parse-back-end): while-waiting research` — docs-only, merge whenever
7. **#74** `docs(agents): strengthen repo-target rule` — docs-only, merge whenever (probably first since it's tiny and helps everyone)

**Coordinator (your own):**

8. **#64** `docs(coordinator): sign Phase 0 baseline` — merge after Task 1 finishes (so the scorecard refresh gets the signed baseline state)
9. **#65** `docs(coordinator): publish 2026-04-26 rebuild progress scorecard` — after refresh in Task 1
10. **#66** `docs(coordinator): record Annotate parity evidence` — independent
11. **#67** `docs(coordinator): move task queueing from main-branch PRs to .hermes/handoffs/` — last; once merged, retire `docs/plans/2026-04-26-parse-*-next-task-*.md` files in a follow-up cleanup PR

**Ordering principle:** docs-only PRs (#74, #70, #72, #66, #67) can merge in any order anytime. Implementation PRs need conflict-aware ordering. Your own coordinator PRs (#64, #65) should land after the work they reference is signed off (Task 1 refreshes #65's content; #64's baseline is already signed).

After the wave settles, **do another scorecard refresh** in a follow-up commit to PR #65 (or a tiny chase PR) so the post-wave numbers are recorded.

## Task 4 — Compare parity evidence pass

Same methodology as PR #66 (Annotate). Apply to **Compare** as the next P0 surface from `option1-parity-inventory.md` §5.1.

### Deliverable

`docs/reports/2026-04-27-compare-parity-evidence.md` (use tomorrow's date if work happens overnight; today's if same-session)

Plus per-flow evidence files under `.hermes/reports/parity/compare/` mirroring the Annotate pass's structure.

### Flows to record (P0 from `option1-parity-inventory.md` §5.1)

1. Concept × speaker table render (load Saha01 fixture, verify table shape matches)
2. Cognate accept on a known-cognate pair → reload → assert persistence
3. Cognate split on a known-mismatch pair → reload → assert persistence
4. Cognate merge → reload → assert persistence
5. Cognate cycle through colors → assert visual state matches oracle
6. Borrowing mark on one form → reload → assert
7. Notes persistence on one concept → reload → assert
8. Enrichment edit on one cell → reload → assert

For each flow: PASS / FAIL / DEVIATION + 1-line note + evidence file (text log; screenshot only if visual differs).

### Caveat to record at the top

Oracle Compare may have its own instabilities you haven't seen yet (just like Annotate's TranscriptionLanes hook-order crash). If oracle crashes on a Compare flow, file an oracle issue (same pattern as #230) and document the crash as evidence rather than treating it as a parity failure on rebuild's part. Same logic as PR #66 §"oracle Annotate is not a clean gold standard."

### Out-of-scope inside this task

- Tags parity (separate task, queue after Compare)
- AI/chat parity (P1, deferred)
- Implementation work or fixes — evidence only

## Task 5 — Tags parity (deferred to next handoff after Task 4 lands)

Same methodology, applied to Tags surface. Will queue separately once Compare evidence is in.

## Acceptance summary

Cumulative across this handoff:

- PR #65 refreshed with post-merge numbers, committed and pushed
- 1–2 oracle issues filed for the source_index.json path-separator bug
- Merge wave progressed: most or all of #68–#74 merged in dependency order
- `docs/reports/2026-04-27-compare-parity-evidence.md` exists with all 8 P0 flows recorded

## Out-of-band notes

- Don't restart `auto/parse-builder` / `auto/parse-back-end` lanes yet — wait for the merge wave to settle.
- Don't prune the ~40 rebuild worktrees in this task — separate hygiene pass.
- The 8 rebuild backend test failures are now classified in PR #64; the 5 fixture-issue ones can be re-tested locally to confirm classification before this handoff completes — optional, not required.
- If the merge wave reveals a conflict you can't quickly resolve (e.g., #69 vs #71 vs #73 stacking conflict), prefer asking parse-builder to rebase rather than rebasing yourself — preserves agent autonomy.
