---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #84 partially complete (Compare parity shipped as #87, #81/#82 merged); remaining items to finish
related_skills:
  - parse-rebuild-three-lane-pr-coordination
  - parse-rebuild-progress-scorecard
  - parse-rebuild-annotate-parity-audit
  - parse-rebuild-worktree-hygiene
  - parse-mc-workflow
---

# parse-gpt next task — finish Tags parity, merge tail, queue mcp_adapter PR 1, hygiene

**Why this exists:** PR #84's burst was excellent — Compare parity shipped as #87, merge wave continued cleanly (5 more PRs landed), parse-builder's orchestrator pass is at PR C with ParseUI.tsx down to 2109 LoC (close to ≤1800 target). Three PR #84 items still unfinished + new merge tail accumulated.

## Working environment

Same rule as everywhere — see AGENTS.md (PR #74) and the new screenshot convention from PR #89 (markdown links, not inline embeds). Verify rebuild clone + `--repo TarahAssistant/PARSE-rebuild` before any push.

## Task 1 — Finish merge tail (do first, small)

5 PRs open and mergeable:

| PR | What | Action |
|---|---|---|
| **#83** | parse-back-end PR 80 follow-up research | Merge — docs only, just records the sister-bug audit + chat_tools PR 2 pre-research outputs |
| **#84** | your own previous handoff | Self-merge — task tracker |
| **#85** | parse-back-end chat_tools PR 2 execute handoff | Merge — small docs handoff aligning #81 + #83 for parse-back-end |
| **#89** | AGENTS.md screenshot link convention | Merge — tiny docs PR, fixes a real recurring problem |
| **#90** | parse-builder TranscriptionLanes handoff | Merge — docs handoff for the next monolith |

Plus expect parse-back-end's chat_tools PR 2 implementation to appear (predicted: ~500 LoC reduction in chat_tools.py to ~4910). Merge that when it lands.

Plus parse-builder's PR C (useParseUIPipeline hook) — should appear shortly. Merge that when it lands and ParseUI.tsx will hit the floor.

## Task 2 — Tags parity evidence pass (P0, deferred from PR #78 task 3 AND PR #84 task 2)

This has now been deferred twice. Time to ship.

Same methodology as PR #66 (Annotate) and PR #87 (Compare).

### Deliverable

`docs/reports/2026-04-27-tags-parity-evidence.md`

Per-flow evidence files under `.hermes/reports/parity/tags/`.

### Flows to record (P0 from `option1-parity-inventory.md` §5.1.3)

1. Tag create — name + swatch + submit → assert appears in store + UI
2. Tag rename — edit existing → assert UI updates + store mutation
3. Tag delete — confirm dialog → assert removal
4. Tag merge — select source + target → assert source removed, target retains
5. Bulk-state change — multi-select → bulk action → assert each tag mutated
6. Persistence after reload — create tag, reload Compare mode, assert survives
7. Empty state — fresh workspace → assert empty-state UI + create affordance

Same "oracle is not a clean gold standard" caveat from PR #66/#87. If oracle Tags has crash/instability, file an oracle issue (pattern from #230) and document the crash as evidence.

**Behavior reference**: post-#63 ManageTagsView extraction. That's the new rebuild-side reference for Tags.

**Screenshot rule**: markdown links, not embeds (per PR #89 / AGENTS.md). Example: `[Screenshot: tag merge dialog](.hermes/reports/parity/tags/04-tag-merge.png)`.

## Task 3 — Refresh scorecard with post-wave numbers

PR #65 / #87 are stale. Concrete numbers to refresh:

- ParseUI.tsx: was 4404 at queue time → currently **2109 LoC** (down 52% — huge!)
- chat_tools.py: was 6408 → currently **5428 LoC** (PR 2 will drop to ~4910 when it lands)
- mcp_adapter.py: still **2050 LoC** (next backend monolith target)
- TranscriptionLanes.tsx: **943 LoC** (next frontend monolith — handoff queued in PR #90)
- 24h merged PR count: substantially higher than the last refresh (estimate before counting)
- Add coordination state rows: Compare parity evidence (#87) shipped; AGENTS.md screenshot convention (#89) shipped

Commit to PR #65's branch as a follow-up commit, OR a small chase PR — your call.

## Task 4 — Queue parse-back-end's mcp_adapter PR 1 (env_config.py extraction)

parse-back-end's PR #72 architecture audit identified `env_config.py` as the lowest-risk PR 1 candidate for the mcp_adapter decomposition. Once chat_tools PR 2 ships and clears, parse-back-end needs a follow-on prompt.

**Note**: I'll likely open this handoff myself if it makes sense before parse-gpt picks up this task. If the handoff (`handoff/parse-back-end-mcp-adapter-pr1-env-config`) already exists when you read this, just merge it; don't open a duplicate. If it doesn't exist, open it per the spec in PR #84:

- Branch: `handoff/parse-back-end-mcp-adapter-pr1-env-config`
- File: `.hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-pr1-env-config.md`
- PR title: `handoff(parse-back-end): mcp_adapter PR 1 — extract env_config.py`
- Source file: `python/adapters/mcp_adapter.py` (NOT `python/ai/mcp_adapter.py`)
- Reference parse-back-end's PR #72 audit doc as the source of truth
- Hard rule: do NOT touch FastMCP private API mutation in this PR
- ~50 lines max

## Task 5 — Hygiene (defer if budget tight)

- **Restart `auto/parse-builder` and `auto/parse-back-end` lanes** — Phase 0 baseline signed (#64), AGENTS.md repo-target rule live (#74), agents have demonstrated discipline. Reference the new `.hermes/handoffs/<agent>/` location.
- **Worktree pruning** — ~40 rebuild worktrees, many for closed/merged branches. Use `parse-rebuild-worktree-hygiene` skill. Output: doc under `.hermes/handoffs/parse-gpt/` summarizing what was pruned + which were preserved.

## Task 6 — AI/chat parity pass (P1, defer if budget tight)

Same methodology, lower priority than Tags. Defer to next handoff if Tasks 1-5 use up the budget.

## Acceptance summary

Cumulative across this handoff:

- All 5+ open mergeable PRs merged (including new in-flight ones from parse-builder and parse-back-end)
- Tags parity evidence pass complete with all 7 P0 flows recorded (markdown link screenshots)
- Scorecard refreshed with post-wave numbers (no TBDs)
- mcp_adapter PR 1 handoff opened for parse-back-end (or merged if I opened it earlier)
- Hygiene + AI/chat parity done or explicitly deferred

## Out-of-band notes

- **Don't queue another parse-builder ParseUI.tsx pass** — PR #82's escape hatch covers it; PR C should hit ≤1800 (or the floor) and parse-builder pivots to TranscriptionLanes via PR #90 handoff.
- **Path-separator fix sync to oracle** still requires explicit user approval. Don't open the oracle PR autonomously.
- The 10 oracle failing backend tests still need classification — defer to a future burst.
- If chat_tools PR 2 reveals that the PR 3 grouping needs adjustment, surface as a deviation note in your task-log; don't silently re-scope parse-back-end's next handoff.
