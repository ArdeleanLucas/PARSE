---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #75 should be ~done (merge wave + oracle issues + scorecard refresh)
  - Pick up immediately after #75's last commit lands
related_skills:
  - parse-rebuild-three-lane-pr-coordination
  - parse-rebuild-progress-scorecard
  - parse-rebuild-annotate-parity-audit
  - parse-rebuild-worktree-hygiene
  - parse-mc-workflow
---

# parse-gpt next task — finish merge wave, lift chat_tools wait-rule, run Tags + AI/chat parity, hygiene

**Why this exists:** PR #75's burst was excellent — 11 PRs merged (#64–#70, #72, #74, plus the parse-builder/back-end implementations), 2 oracle issues filed (#231, #232), merge wave most of the way through. Five concrete next tasks remain, listed in priority order.

## Working environment

Same rule as everywhere — see [PR #74 / AGENTS.md](https://github.com/TarahAssistant/PARSE-rebuild/blob/main/AGENTS.md#repo-target-rule-read-before-opening-any-pr). Verify rebuild clone + `--repo TarahAssistant/PARSE-rebuild` before any push. PR #229 / #225 / #226 cautionary tales already documented.

## Task 1 — Finish the merge wave (5 PRs left open)

| PR | State | Notes |
|---|---|---|
| **#71** lift reference-form parsing | MERGEABLE, CLEAN | parse-builder rebased onto current main. Safe to merge first. |
| **#73** extract annotate helpers | **CONFLICTING** (now stale after #69 merged) | parse-builder needs to rebase again. Comment on the PR asking for rebase, then merge once green. |
| **#75** your own handoff | MERGEABLE | Merge whenever — docs only |
| **#76** parse-builder Compare helpers handoff | MERGEABLE | Docs only — merge whenever |
| **#77** `fix(chat_tools): normalize project-relative display path` | MERGEABLE | parse-back-end's path-separator real-bug fix using the root cause they identified. Merge after a quick review — verify it changes `_display_readable_path` at `chat_tools.py:5316-5321` to `.as_posix()`. After merge, the 2 failing tests `test_import_processed_speaker_write_copies_assets_and_builds_workspace_files` and `test_import_processed_speaker_preserves_existing_sources_and_clears_stale_optional_metadata` should pass. Re-run rebuild backend gate; if green, **post a follow-up comment on oracle issues #231 + #232** linking the rebuild fix as the canonical patch (oracle should cherry-pick / mirror it). |

After all 5 merge, **refresh the scorecard one more time** (commit to PR #65's branch or a new tiny chase PR — your call). Numbers after the wave: ParseUI.tsx ~2469 LoC if #71 + #73 land + #76 doesn't yet, ~2354 if #76 also lands. Worth recording for the parity baseline.

## Task 2 — Lift the chat_tools wait-rule for parse-back-end

PR #68 (chat_tools PR 1, the cherry-pick replay) merged in your last burst. The wait-rule from `docs/plans/2026-04-26-parse-back-end-next-chat-tools-decomposition.md` (now at `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-decomposition.md` per the migration in PR #67) said parse-back-end must wait for PR #68 review/merge before starting PR 2. That gate is now clear.

Open a small handoff PR signaling resumption:

- Branch: `handoff/parse-back-end-chat-tools-wait-rule-cleared`
- File: `.hermes/handoffs/parse-back-end/2026-04-26-chat-tools-pr2-resume.md` with frontmatter pointing at the cleared gate, the next task (chat_tools PR 2 — acoustic starters + pipeline orchestration per the original PR #59 grouping), and the rebuild-repo guard.
- PR title: `handoff(parse-back-end): chat_tools PR 2 unblocked — PR #68 merged`

This is small (40-50 lines max). Same pattern as my handoff PRs (#70, #72, #75, #76).

## Task 3 — Tags parity evidence pass

Same methodology as PR #66 (Annotate). Tags is the second P0 surface from `option1-parity-inventory.md` §5.1.

### Deliverable

`docs/reports/2026-04-27-tags-parity-evidence.md` (use today's or tomorrow's date as appropriate)

Per-flow evidence files under `.hermes/reports/parity/tags/`.

### Flows to record (P0 from `option1-parity-inventory.md` §5.1.3)

1. Tag create — name + swatch picked + submit → assert appears in store + UI
2. Tag rename — edit existing tag → assert UI updates + store mutates
3. Tag delete — confirm dialog → assert removal from store + UI
4. Tag merge — select source + target → assert source removed, target retains
5. Bulk-state change — multi-select → apply bulk action → assert each tag mutated
6. Persistence after reload — create tag, reload Compare mode, assert survives
7. Empty state — fresh workspace with no tags → assert empty-state UI + create affordance

### Caveat to record at top

Use the same "oracle is not a clean gold standard" framing from PR #66. If oracle Tags has its own crash/instability, file an oracle issue (same pattern as #230) and document the crash as evidence rather than treating it as rebuild failure.

**Bonus**: parse-builder's PR #63 extracted ManageTagsView into its own component. Run the parity pass against the post-#63 main (rebuild side) — that's the new behavior reference for Tags going forward.

## Task 4 — Refresh scorecard with post-wave numbers

PR #65's content is now stale after the 11-PR wave. Numbers worth refreshing in a follow-up commit (or chase PR):

- ParseUI.tsx LoC: 4404 → 2926 (current, before #71/#73/#76)
- chat_tools.py LoC: 6408 → likely down ~980 LoC after PR #68 merged (parse-back-end's report said 5428)
- 24h merged PR count: was 39 at last refresh; should be ~50+ now
- Add a "post-wave coordination state" section noting: Phase 0 signed (#64), handoff convention live (#67), AGENTS.md repo-target rule live (#74), 2 oracle path-separator issues filed (#231, #232), 1 oracle hook-order issue filed (#230)

## Task 5 — AI/chat parity evidence pass

Same methodology, P1 surface from `option1-parity-inventory.md` §5.2. Lower priority than Tags (P0). Defer to a separate handoff if Tasks 1-4 use up the iteration budget.

Flows: chat session start, send message, render markdown response, tool invocation surface, error state, session reset.

## Task 6 — Hygiene (low-priority, defer if budget tight)

- **Restart `auto/parse-builder` and `auto/parse-back-end` lanes** — Phase 0 baseline is signed (#64 merged) and merge wave has settled, so the autonomy lanes can resume without contract drift risk. Same instructions as before but reference the new `.hermes/handoffs/<agent>/` location for prompts.
- **Worktree pruning** — there are ~40 rebuild worktrees under `/home/lucas/gh/worktrees/PARSE-rebuild/...`, many for closed/merged branches. Use `parse-rebuild-worktree-hygiene` skill to classify and prune without losing in-progress work. Output: a doc summarizing what was pruned.

## Acceptance summary

Cumulative across this handoff:

- All 5 remaining open PRs (#71, #73 after rebase, #75, #76, #77) merged
- chat_tools wait-rule lift handoff opened for parse-back-end
- Tags parity evidence pass complete with all 7 P0 flows recorded
- Scorecard refreshed with post-wave numbers
- AI/chat parity pass either done or deferred to next handoff with explicit reasoning
- Hygiene tasks done or explicitly deferred

## Out-of-band notes

- ParseUI.tsx target: ≤1800 LoC. After #71/#73/#76 land, projected at ~2354. **One more parse-builder pass needed** — the residual ParseUI orchestrator logic + modal-management. Do not queue that here; will be a separate parse-builder handoff after #76 lands.
- Don't file new oracle issues for the 6 fixture-issue rebuild test failures (parse-back-end's classification). Those are environment/CI issues, not behavior bugs — let them surface naturally if they break a real workflow.
- The 10 oracle backend test failures still need their own classification pass (parse-back-end did the rebuild side; oracle side hasn't been done). Defer to a future coordinator burst — not in this handoff.
- If parse-back-end's PR 2 of chat_tools opens before this handoff completes, treat it like any other implementation PR in the merge order — don't block on it.
