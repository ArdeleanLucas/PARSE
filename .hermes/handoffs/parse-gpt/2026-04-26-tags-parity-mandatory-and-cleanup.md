---
agent: parse-gpt
queued_by: opus-coordinator
queued_at: 2026-04-26
status: queued
depends_on:
  - PR #92 should be ~complete (most tasks done; Tags parity is the lingering item)
related_skills:
  - parse-rebuild-annotate-parity-audit
  - parse-rebuild-progress-scorecard
  - parse-rebuild-three-lane-pr-coordination
  - parse-rebuild-worktree-hygiene
  - parse-mc-workflow
---

# parse-gpt next task — Tags parity (MANDATORY) + scorecard refresh + cleanup

**Why this exists:** Tags parity has now been deferred **3 times** (PR #78 task 3, PR #84 task 2, PR #92 task 2). It cannot be deferred a fourth. Per the new `option1-parity-inventory.md` §12 (Current evidence priority), Tags is at the top of the next-up list. This handoff makes it **the mandatory first task**, with everything else explicitly secondary.

## Working environment

Same rule. AGENTS.md PR #74. Markdown-link screenshots per PR #89. Reference parity inventory §11 (Accepted oracle deviations) when recording any oracle-side instability.

## Task 1 (MANDATORY) — Tags parity evidence pass

This is the **non-negotiable first task** of this handoff. Do not advance to Tasks 2-4 until Tags parity evidence is published.

### Methodology

Same as your PR #66 (Annotate) and PR #87 (Compare). Paired runs against oracle and rebuild on the Saha01 fixture; per-flow text/screenshot evidence under `.hermes/reports/parity/tags/`; summary doc at `docs/reports/2026-04-27-tags-parity-evidence.md` (or today's date if same-session).

### Behavior reference

**Rebuild side**: post-#63 `ManageTagsView` extracted into `src/components/compare/ManageTagsView.tsx`. That's the new behavior reference for Tags going forward.

**Oracle side**: tags-mode UI on oracle's current main. Reference parity inventory §11 for accepted deviations; if oracle Tags has its own crash/instability, file an oracle issue (pattern from #230) and document the crash as DEVIATION rather than rebuild failure.

### Flows to record (P0 from `option1-parity-inventory.md` §5.1.3)

1. Tag create — name + swatch + submit → assert appears in store + UI on both
2. Tag rename — edit existing → assert UI updates + store mutation on both
3. Tag delete — confirm dialog → assert removal from store + UI on both
4. Tag merge — select source + target → assert source removed, target retains on both
5. Bulk-state change — multi-select → bulk action → assert each tag mutated on both
6. Persistence after reload — create tag, reload Compare mode, assert survives on both
7. Empty state — fresh workspace → assert empty-state UI + create affordance on both

### Acceptance

- All 7 flows recorded with PASS / FAIL / DEVIATION status + 1-line note + evidence file (markdown link to `.hermes/reports/parity/tags/<flow>.png` or `.txt`)
- Screenshot SHA256s verified distinct (per AGENTS.md screenshot section + PR #97 standard)
- Summary doc at `docs/reports/2026-04-27-tags-parity-evidence.md`
- Update `option1-parity-inventory.md` §12 Current evidence priority — strike Tags from top of list, promote AI/chat to position 1

## Task 2 — Refresh scorecard with current numbers

Numbers worth refreshing in `docs/reports/2026-04-26-rebuild-progress-scorecard.md` (or a follow-up commit / chase PR):

- ParseUI.tsx: was 4404 → currently **2035 LoC** (54% reduction from oracle)
- chat_tools.py: was 6408 → currently **4850 LoC** (24% reduction from oracle)
- Plus incoming: chat_tools.py after PR 3/4 → ~2500 LoC (61% reduction)
- ParseUI.tsx after TranscriptionLanes/BatchReportModal: continues shrinking
- mcp_adapter.py: still 2050 (next monolith — handoff queued via PR #92 task 4)
- Add coordination state rows: Option 3 cancelled (PR #98), oracle sync PRs authorized (PR #99), Tags parity evidence shipped (Task 1 above)

## Task 3 — Update parity inventory after oracle sync PRs land

After parse-gpt's PR #99 oracle sync PRs (path-separator + TranscriptionLanes hook-order) merge on oracle:

- Update `option1-parity-inventory.md` §11 (Accepted oracle deviations) — mark the two synced bugs as **RESOLVED** with sync PR links
- Update PR #66 (Annotate parity evidence) with a follow-up note: oracle hook-order crash now fixed; future Annotate parity passes against oracle should not encounter this deviation
- Close oracle issues #230, #231, #232 once their respective oracle PRs merge

## Task 4 — Worktree pruning hygiene (defer if budget tight)

~40 rebuild worktrees on disk, many for closed/merged branches. Use `parse-rebuild-worktree-hygiene` skill. Output: doc under `.hermes/handoffs/parse-gpt/` summarizing what was pruned + which were preserved (any with active in-progress work).

## Acceptance summary

Cumulative across this handoff:

- ✅ Tags parity evidence pass complete with all 7 P0 flows recorded — **mandatory, non-negotiable**
- Scorecard refreshed with current post-wave numbers
- Parity inventory §11 updated when oracle sync PRs land
- Worktree pruning done OR explicitly deferred to next handoff with reasoning

## Out-of-band notes

- **Don't queue another parse-builder ParseUI.tsx pass** — file is essentially done (2035 LoC, hits ≤1800 floor implicitly through TranscriptionLanes/BatchReportModal extractions next-door)
- **Don't queue mcp_adapter PR 2+** — parse-back-end's PR 4 + mcp_adapter PR 1 are queued via my new parallel handoff; PRs 2-5 of mcp_adapter come after PR 1 lands
- **Auto-* lanes stay coordinator-driven for now** per Lucas decision 2026-04-26 (sync PR #96)
- **AI/chat parity** moves to position 1 of inventory §12 after Tags ships — that becomes your next handoff's primary task
- The 10 oracle failing backend tests still need classification — defer further; not blocking parity work
