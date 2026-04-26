---
type: coordinator-sync
date: 2026-04-26 evening
authored_by: opus-coordinator
purpose: align all lanes on current state, decisions made, decisions deferred, next 48h priorities
---

# Coordinator sync — 2026-04-26 evening

This doc is the single source of truth for "where is the rebuild right now and what comes next." Future sessions / new agents should be able to read this in 5 minutes and act, without reconstructing state from the PR queue.

## State snapshot

**SHAs:**
- Rebuild origin/main: `26291dc027`
- Phase 0 baseline (frozen): rebuild `f9aa3db1aa`, oracle `0951287a81`
- Oracle has not moved since 2026-04-26 (`0951287a81` unchanged)

**Monolith reduction (rebuild vs oracle baseline):**

| File | Oracle | Rebuild main | Incoming | Δ from oracle |
|---|---:|---:|---:|---:|
| `src/ParseUI.tsx` | 5328 | 2109 | 2035 (PR #94) | **−61.8%** |
| `python/ai/chat_tools.py` | 6408 | 5428 | 4850 (PR #91) | **−24.3%** |
| `python/server.py` | 8972 | 7757 | — | **−13.5%** |
| `python/adapters/mcp_adapter.py` | 2050 | 2050 | — | 0% (untouched) |
| `python/ai/provider.py` | 1907 | 1907 | — | 0% (untouched) |

**Process throughput:**
- 61 PRs merged since rebuild started (~24h)
- 10 PRs currently open
- 144 test files (59 frontend + 85 backend)
- 122 extracted module files (95 React + 27 Python)

**Parity evidence coverage:**
- Annotate (P0): ✓ shipped (#66) — recorded oracle hook-order crash as deviation
- Compare (P0): ✓ shipped (#87)
- Tags (P0): ❌ **twice-deferred — next priority**
- AI/chat, Import, Compute/report, CLEF, Job diagnostics (P1): ❌ all unstarted

**Coordination scaffolding:**
- ✓ Phase 0 baseline signed (#64)
- ✓ AGENTS.md repo-target rule (#74)
- ✓ Handoff convention `.hermes/handoffs/<agent>/` (#67)
- ✓ Progress scorecard (#65 + #87)
- ✓ Screenshot link convention (#89)
- ❌ Worktree pruning (~40 worktrees on disk)
- ❌ Auto-* lanes restart deferred

## Active lane status (as of this sync)

| Lane | Current | Next |
|---|---|---|
| **parse-builder** | PR C in review (#94 useParseUIPipeline) | TranscriptionLanes.tsx decomposition (handoff #90) |
| **parse-back-end** | PR 2 in review (#91 acoustic+pipeline) | sister-bug fix at chat_tools.py:2271 + chat_tools PR 3 (handoff #93) |
| **parse-gpt** | merge tail draining + Tags parity queued | mcp_adapter PR 1 handoff for parse-back-end (handoff #92) |

## Decisions made (recorded here for future reference)

1. **Wait-rule from PR #59/#81 is relaxed.** AGENTS.md guard (#74) plus demonstrated lane discipline (only one wrong-repo incident, recovered) make per-PR explicit lift handoffs unnecessary. Normal review cadence applies.
2. **Tags parity is the next P0 evidence priority.** Has been deferred from PR #78 task 3 and PR #84 task 2. Cannot be deferred a third time without explicit Lucas escalation.
3. **mcp_adapter env_config.py is the next backend monolith extraction** after chat_tools PRs 2-4 land. parse-back-end's PR #72 audit identifies it as the lowest-risk first slice.
4. **TranscriptionLanes.tsx is the next frontend monolith** after ParseUI.tsx hits its floor (≤1800 LoC or PR #82's escape hatch). Handoff queued in #90.
5. **chat_tools PR 2 was a 2-module split, not single bundle.** parse-back-end's pre-research (PR #83) recommended this; the PR #59 prompt's single-bundle suggestion was over-aggressive.
6. **PR-target screenshots use markdown links, not inline embeds.** Private repo means inline `<img src="raw.githubusercontent.com/...">` 404s in PR bodies. Documented in AGENTS.md via #89.

## Open decisions for Lucas (blocking items I can't decide for you)

1. **Sync the path-separator fix (#77 / MC-323) to oracle?** AGENTS.md exception case requires explicit per-task approval. Bug exists on oracle (live thesis runtime). Affects `import_processed_speaker_*` flows. Cherry-pick is mechanically simple.
2. **Sync the TranscriptionLanes hook-order fix (rebuild PR #19) to oracle?** Same exception case. Oracle issue #230 documents the crash; the fix exists in rebuild but oracle hasn't received it. Lucas's `/annotate` workflow on the live thesis runtime is broken until either the fix lands on oracle or the dev server is repointed.
3. **Option 3 (desktop platform) timeline.** The plan calls for desktop platform work after Option 1 monolith decomposition completes. Current pace suggests Option 1 done-state is 3-5 days out. Should desktop work start in parallel with the last monoliths (mcp_adapter / provider) or wait until Option 1 fully closes?
4. **Repo visibility — flip rebuild to public?** Would fix the screenshot-404 root cause permanently and improve discoverability if you ever want to share the rebuild. Current downside: any private API keys or fixture paths committed accidentally would be exposed (audit before flipping).
5. **Auto-`*` lane restart.** Both `auto/parse-builder` and `auto/parse-back-end` have been quiet since the merge wave started. Restart against the new handoff convention, or keep coordinator-driven for the duration of the rebuild?

## Two structural findings worth recording

These came out of dogfooding the rebuild and need to be reflected in plan documents:

1. **Oracle is not a clean parity reference.** Oracle has its own bugs (Annotate hook-order crash on Saha01 fixture, 10 failing backend tests, path-separator real-bug). Parity evidence has been recording these as "accepted deviations," but `option1-parity-inventory.md` was written assuming oracle-as-immutable-spec. The inventory needs updating (this PR adds an "Accepted oracle deviations" section).
2. **Velocity is unevenly distributed across lanes.** Frontend (ParseUI.tsx) raced 5328 → 2035 (−62%) in one day. Backend is steady but slower. Parity evidence is lagging worst (25% complete). If the rebuild is to be confidently promoted to Option 3 desktop pivot, parity needs to catch up to monolith reduction.

## Next 48-hour priorities

In order of leverage:

1. **Tags parity evidence pass** (parse-gpt) — single biggest unblock for "is the rebuild actually behaviorally equivalent to oracle?"
2. **Land the merge tail** (parse-gpt) — 10 open PRs need draining, including the two big implementations (#91 chat_tools PR 2, #94 ParseUI PR C). After these merge, ParseUI.tsx hits floor and chat_tools.py hits −24%.
3. **Sister-bug fix at chat_tools.py:2271** (parse-back-end, post-#91 merge) — small one-line stacked fix
4. **chat_tools PR 3 pre-research** (parse-back-end, post-#91 merge) — same pattern as PR #83
5. **mcp_adapter PR 1 handoff queue** (parse-gpt) — small docs PR pointing at PR #72 audit
6. **TranscriptionLanes decomposition starts** (parse-builder, post-PR-C merge) — handoff already queued in #90

After 48h: AI/chat parity, Import parity, mcp_adapter PRs 2-3, server.py more passes, oracle backend test classification.

## What is NOT a priority right now

- Worktree pruning (cosmetic; can wait for a quiet hour)
- Auto-* lane restart (coordinator-driven cadence is working)
- AI/chat parity (P1; queued behind Tags)
- Option 3 desktop platform work (premature; Option 1 needs to be near-done)
- Oracle backend test classification (deferred; not blocking parity work)
- Public repo flip (Lucas decision, not blocking)

## How this sync was generated

Coordinator review of: PR queue (open + recent merges), all parity evidence files, scorecard, lane task-logs, AGENTS.md, plan documents. No implementation code touched. No agent review needed — this is meta-coordination state, not a task assignment. Lucas reviews + decides on the 5 open items above.

## Related plan amendments in this same PR

- `docs/plans/option1-parity-inventory.md` — added "Accepted oracle deviations" + "Current evidence priority" sections
- `docs/plans/option1-phase0-shared-contract-checklist.md` — added baseline status note clarifying frozen-vs-current SHAs
