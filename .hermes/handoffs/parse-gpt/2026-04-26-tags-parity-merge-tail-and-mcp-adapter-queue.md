---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #78 should be ~complete (5 PRs merged in the burst, wait-rule lift opened as PR #81)
  - Pick up immediately after PR #78's last action lands
related_skills:
  - parse-rebuild-three-lane-pr-coordination
  - parse-rebuild-progress-scorecard
  - parse-rebuild-annotate-parity-audit
  - parse-rebuild-worktree-hygiene
  - parse-mc-workflow
---

# parse-gpt next task — Tags parity, finish merge tail, queue mcp_adapter PR 1, hygiene

**Why this exists:** PR #78's burst was excellent. 5 PRs merged (#79, #75, #76, #78, #80), wait-rule lift handoff shipped as #81, path-separator fix cross-linked to oracle. But four PR #78 tasks remain incomplete: Tags parity (P0), scorecard refresh, AI/chat parity (P1), hygiene. Plus new follow-on coordination work has accumulated.

This handoff covers the finish of PR #78 plus queuing the next backend monolith (mcp_adapter.py) so parse-back-end has a follow-on after they ship chat_tools PR 2.

## Working environment

Same rule as everywhere — see [PR #74 / AGENTS.md](https://github.com/TarahAssistant/PARSE-rebuild/blob/main/AGENTS.md). Verify rebuild clone + `--repo TarahAssistant/PARSE-rebuild` before any push.

## Task 1 — Finish merge tail (small, do first)

Two PRs open right now:

| PR | State | Action |
|---|---|---|
| **#81** wait-rule lift handoff | MERGEABLE | Self-merge — your own task 2 deliverable from PR #78 |
| **#82** parse-builder orchestrator pass handoff | MERGEABLE | Merge — small docs PR |

After these merge, parse-back-end's chat_tools PR 2 should appear in the queue (they have the unblock signal from #81 once it lands). parse-builder's PR A from #82's three-PR sequence should also start appearing.

## Task 2 — Tags parity evidence pass (P0, deferred from PR #78 task 3)

Same methodology as PR #66 (Annotate). Tags is the second P0 surface from `option1-parity-inventory.md` §5.1.3.

### Deliverable

`docs/reports/2026-04-27-tags-parity-evidence.md` (use today's or tomorrow's date)

Per-flow evidence files under `.hermes/reports/parity/tags/`.

### Flows to record

1. Tag create — name + swatch picked + submit → assert appears in store + UI
2. Tag rename — edit existing tag → assert UI updates + store mutates
3. Tag delete — confirm dialog → assert removal from store + UI
4. Tag merge — select source + target → assert source removed, target retains
5. Bulk-state change — multi-select → apply bulk action → assert each tag mutated
6. Persistence after reload — create tag, reload Compare mode, assert survives
7. Empty state — fresh workspace with no tags → assert empty-state UI + create affordance

Same "oracle is not a clean gold standard" caveat from PR #66. If oracle Tags has crash/instability, file an oracle issue (pattern from #230) and document the crash as evidence.

**Key note:** Run the rebuild side against post-#63 main (ManageTagsView extracted into its own component). That's the new behavior reference for Tags going forward.

## Task 3 — Refresh scorecard (post-wave numbers)

PR #65 is now stale after the wave. Numbers worth refreshing in a follow-up commit (or chase PR):

- ParseUI.tsx: was 4404 → currently **2319 LoC** (predicted ~1800 after PR #82 lands)
- chat_tools.py: was 6408 → currently **5428 LoC** (after PR #68; will drop further when chat_tools PR 2 ships)
- mcp_adapter.py: 2050 LoC (still untouched — next backend monolith target)
- 24h merged PR count: ~50+ now (was 39 at last refresh)
- Add rows for new coordination state: AGENTS.md repo-target rule live (#74), wait-rule lift shipped (#81), path-separator real-bug fixed (#77 + oracle issues #231/#232 cross-linked)

## Task 4 — Queue parse-back-end's mcp_adapter PR 1 (env_config.py extraction)

parse-back-end's PR #72 architecture audit identified `env_config.py` as the lowest-risk PR 1 candidate for the mcp_adapter decomposition. Once chat_tools PR 2 ships and clears, parse-back-end needs a follow-on prompt.

Open a small handoff PR following the convention:

- Branch: `handoff/parse-back-end-mcp-adapter-pr1-env-config`
- File: `.hermes/handoffs/parse-back-end/2026-04-26-mcp-adapter-pr1-env-config.md`
- PR title: `handoff(parse-back-end): mcp_adapter PR 1 — extract env_config.py`

Spec to include:
- Source file: `python/adapters/mcp_adapter.py` (NOT `python/ai/mcp_adapter.py` — common confusion; flag explicitly)
- Target: `python/adapters/mcp/env_config.py` per the audit's proposed structure
- Reference parse-back-end's PR #72 audit doc as the source of truth for what to extract
- Hard rule: do NOT touch FastMCP private API mutation (`mcp._tool_manager._tools`) in this PR — that's the highest-risk seam and needs its own dedicated handoff
- Test surface: pair with `python/adapters/mcp/test_env_config.py`
- Same Working environment guard

Estimated PR length: ~50 lines max — most of the spec lives in the parse-back-end audit doc you're referencing.

## Task 5 — Hygiene (low-priority, defer if budget tight)

- **Restart `auto/parse-builder` and `auto/parse-back-end` lanes** — Phase 0 baseline is signed (#64 merged), merge wave has settled, lanes can resume. Reference the new `.hermes/handoffs/<agent>/` location.
- **Worktree pruning** — ~40 rebuild worktrees, many for closed/merged branches. Use `parse-rebuild-worktree-hygiene` skill. Output: doc under `.hermes/handoffs/parse-gpt/` summarizing what was pruned + which were preserved (any with active in-progress work).

## Task 6 — AI/chat parity pass (P1, defer if budget tight)

Same methodology, lower priority than Tags. P1 surface from `option1-parity-inventory.md` §5.2.

Flows: chat session start, send message, render markdown response, tool invocation surface (now with PR #68's grouped tools), error state, session reset.

Defer to next handoff if Tasks 1-5 use up the iteration budget.

## Acceptance summary

Cumulative across this handoff:

- #81 + #82 merged
- Tags parity evidence pass complete with all 7 P0 flows recorded
- Scorecard refreshed with post-wave numbers (ParseUI.tsx 2319, chat_tools.py 5428, etc.)
- mcp_adapter PR 1 handoff opened for parse-back-end (small docs PR pointing at #72 audit)
- AI/chat parity pass either done or explicitly deferred to next handoff
- Hygiene tasks done or explicitly deferred

## Out-of-band notes

- Don't queue another parse-builder ParseUI.tsx pass beyond [PR #82](https://github.com/TarahAssistant/PARSE-rebuild/pull/82) — PR #82 has explicit escape-hatch that surfaces if ≤1800 isn't achievable; let parse-builder hit that floor before adding more.
- After parse-back-end's mcp_adapter PR 1 lands, the next mcp_adapter slice (likely `http_callbacks.py` per the audit) becomes a separate handoff.
- The 10 oracle failing backend tests still need classification — defer to a future burst, not this one.
- The path-separator fix (#77, now merged) should be **synced to oracle** as the first controlled-sync PR per AGENTS.md's exception case — but only with explicit user approval per the rule. Surface it as a recommendation in your task-log; don't open the oracle PR yourself unless Lucas signs off.
