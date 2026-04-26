---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #103 mostly complete (Tags parity #113 shipped, parity §11 update #115 shipped)
related_skills:
  - parse-rebuild-annotate-parity-audit
  - parse-rebuild-progress-scorecard
  - parse-mc-workflow
---

# parse-gpt next task — Import/onboarding parity evidence + ongoing coordination

**Why this exists:** Tags parity shipped (PR #113). Parity §11 deviations marked resolved (PR #115). Per `option1-parity-inventory.md` §12 (post-AI-chat-drop ordering), **Import/onboarding is now position 1 of the next-up priority list**.

## Working environment

Same rule. AGENTS.md PR #74. Markdown-link screenshots per PR #89. SHA256 verification standard. **New**: refetch before reporting PR status (per just-opened skill PR).

## Task 1 — Import/onboarding parity evidence pass

Same methodology as PR #66 (Annotate), #87 (Compare), #113 (Tags). P1 surface from `option1-parity-inventory.md` §5.2 — promoted to position 1 of §12 priority list after AI/chat dropped.

### Why this is timely

The path-separator fix synced to oracle (PRs #233, #234) directly affects `import_processed_speaker` flows. A parity pass NOW catches whether the synced fix actually closes the bug on oracle-side imports as well as rebuild-side. Plus: `source_index.json` content is now part of the "accepted oracle deviations RESOLVED" claim from PR #115 — verify it.

### Deliverable

`docs/reports/2026-04-27-import-parity-evidence.md` (or today's date)

Per-flow evidence files under `.hermes/reports/parity/import/`.

### Flows to record

1. **Onboard speaker import** — upload audio + Audition CSV → assert speaker appears + concepts loaded + source_index.json POSIX paths
2. **Processed speaker import (write path)** — copy assets + build workspace files → assert source_index.json POSIX paths (the path-separator bug fix)
3. **Processed speaker import (preserve-existing merge)** — re-import with existing concepts → assert merge semantics + no separator regression
4. **Audition CSV import** — pure CSV → assert concepts created + tier mapping correct
5. **Tag CSV import** — bulk tag application → assert tag store mutation
6. **Empty / error states** — bad CSV, missing audio, invalid speaker name → assert sensible error messages
7. **Persistence after reload** — import speaker, reload Compare/Tags, assert visible

### Critical: verify the path-separator fix on oracle

For flows 2 + 3, explicitly compare `source_index.json` content between oracle and rebuild after the same import. Both should now show forward slashes (per the synced fix in oracle PRs #233/#234). If oracle still shows backslashes, the sync didn't propagate correctly — file an oracle issue before continuing.

### Acceptance

- All 7 flows recorded with PASS / DEVIATION / FAIL status + 1-line note + evidence file (markdown link)
- Screenshot SHA256s verified distinct
- For flows 2+3: explicit `source_index.json` content comparison between oracle and rebuild
- Summary doc at `docs/reports/2026-04-27-import-parity-evidence.md`
- Update `option1-parity-inventory.md` §12 — strike Import from position 1, promote Compute/report modals to position 1

## Task 2 — Continue draining merge tail

5 PRs open at queue time:

| PR | Status | Action |
|---|---|---|
| #114 | MERGEABLE/CLEAN | merge — TranscriptionRunModal grid, 494 LoC win |
| #115 | UNSTABLE→MERGEABLE | self-merge (parity §11 update from your last session) |
| #95, #107, #111, #112 | CONFLICTING/DIRTY | comment requesting rebase already posted; wait for agent rebases |

Don't try to resolve agent-PR conflicts yourself (that's what stalled your prior session per coordinator analysis). Comment + wait + merge when CLEAN.

## Task 3 — Refresh scorecard if numbers shift significantly

The evening scorecard refresh PR #106 (now merged) captured the post-wave numbers. After Import parity ships + a few more PRs land, consider another refresh if monolith deltas shift by >10%.

## Acceptance summary

Cumulative across this handoff:

- Import/onboarding parity: 7 flows recorded with explicit oracle-side path-separator verification
- Merge tail drained as agent rebases land
- Inventory §12 updated — Import struck from position 1
- Optional: scorecard refresh if numbers shift

## Out-of-band notes

- **Don't queue another parse-builder ParseUI/modal pass** — handoffs #101 + #82 + the evening's wins (TranscriptionLanes, BatchReportModal, TranscriptionRunModal) cover that runway. parse-builder's next is annotationStore via the coordinator handoff I just queued.
- **parse-back-end's runway is already queued via #102** (chat_tools PR 4 + mcp_adapter PR 1) — they're handling chat_tools PR 3C now per their own pre-research; PR #102 takes over after.
- The 10 oracle failing backend tests still need classification — long-deferred audit, not blocking parity work, defer further if budget tight.
- After Import parity ships: §12 priority position 1 becomes Compute/report modals (P1). Queue separately when parse-gpt finishes this handoff.
