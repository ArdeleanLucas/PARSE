# PARSE-rebuild progress scorecard — 2026-04-26 evening refresh

**Date:** 2026-04-26 evening
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`
**Rebuild SHA:** `cdb316ca4b` (snapshot at refresh time)
**Oracle repo:** `ArdeleanLucas/PARSE`
**Oracle SHA:** `0951287a812609068933ba22711a8ecd97765f38` (unchanged since baseline)
**Authored by:** opus-coordinator
**Supersedes:** `2026-04-26-rebuild-progress-scorecard.md` (now stale after PR #91/#94 + parse-builder/back-end activity)

---

## TL;DR

- **Browser/workstation runtime health:** `7/10` (improved — TranscriptionLanes hook-order fix sync to oracle authorized via PR #99)
- **Monolith reduction:** `7/10` (substantial improvement — see §1)
- **Parity-evidence coverage:** `4/10` (Annotate + Compare shipped; Tags is mandatory next via PR #103)
- **Desktop-distribution readiness:** `CANCELLED` per Lucas decision 2026-04-26 (PR #98); axis no longer applies

Overall: the rebuild has advanced significantly since the original scorecard. Three structural inflection points landed:

1. **ParseUI.tsx hit the orchestrator-only floor** at 2035 LoC (54% reduction from oracle's 5328) after PRs #61/#62/#63/#69/#71/#73/#79/#88/#94 + #97 (TranscriptionLanes started)
2. **chat_tools.py crossed the 24% reduction threshold** at 4850 LoC (from oracle's 6408) after PR #91 (acoustic + pipeline 2-module split)
3. **Process scaffolding solidified**: AGENTS.md repo-target rule (PR #74), screenshot link convention (PR #89), handoff convention (PR #67), Option 3 cancelled (PR #98), oracle bug-sync authorized (PR #99), evening sync doc (PR #96)

---

## 1. Monolith reduction table — current state

**Axis score:** `7/10`

| File | Oracle LoC | Rebuild LoC | Δ | Δ% | Status |
|---|---:|---:|---:|---:|---|
| `src/ParseUI.tsx` | 5,328 | **2,035** | **−3,293** | **−61.8%** | structurally cracked — orchestrator floor hit |
| `python/ai/chat_tools.py` | 6,408 | **4,850** | **−1,558** | **−24.3%** | in-progress (PRs 3 + 4 queued) |
| `python/server.py` | 8,972 | **7,757** | **−1,215** | **−13.5%** | partial — more HTTP handler passes possible |
| `python/adapters/mcp_adapter.py` | 2,050 | **2,050** | 0 | 0% | next backend monolith (env_config.py PR 1 queued via PR #102) |
| `python/ai/provider.py` | 1,907 | **1,907** | 0 | 0% | untouched (audit pending before extraction) |
| **Total reduced** | **24,665** | **18,599** | **−6,066** | **−24.6%** | |

Plus next-tier frontend monoliths now in flight or queued:

| File | Original LoC | Current LoC | Status |
|---|---:|---:|---|
| `src/components/annotate/TranscriptionLanes.tsx` | 943 | **690** (after PR #97 + #104) | in flight via handoff #90, PRs C/D remaining |
| `src/components/shared/BatchReportModal.tsx` | 843 | 843 | queued via handoff #101 (next monolith after TranscriptionLanes) |
| `src/components/shared/TranscriptionRunModal.tsx` | 792 | 792 | queued (after BatchReportModal) |
| `src/stores/annotationStore.ts` | 753 | 753 | queued (later) |

---

## 2. Parity-evidence coverage

**Axis score:** `4/10` (up from 1/10 — Compare shipped via #87)

| Surface | Tier | Status | Evidence |
|---|---|---|---|
| Annotate | P0 | ✓ shipped | PR #66 (recorded oracle hook-order crash as deviation; sync authorized via #99) |
| Compare | P0 | ✓ shipped | PR #87 |
| Tags | P0 | **MANDATORY next** | PR #103 — twice-deferred, cannot defer again |
| AI/chat | P1 | not started | inventory §12 priority position 2 |
| Import / onboarding | P1 | not started | priority position 3 |
| Compute / report modals | P1 | not started | priority position 4 |
| CLEF | P1 | not started | priority position 5 |
| Job diagnostics | P1 | not started | priority position 6 |

Coverage: 2 of 8 surfaces (25%). Tags pass (mandatory) brings it to 3/8 (37.5%). After AI/chat: 4/8 (50%).

---

## 3. Desktop-distribution readiness

**CANCELLED 2026-04-26** per Lucas decision (PR #98). Option 3 desktop platform pivot is dropped, not deferred. This axis no longer applies. The rebuild's done-state is Option 1 (web/React monolith decomposition + parity evidence) complete.

See `AGENTS.md` § "Scope: Option 1 only" + cancellation banners on `docs/plans/option1-separate-rebuild-to-option3-desktop-platform.md` and `docs/desktop_product_architecture.md`.

---

## 4. Velocity (24h refresh)

**75 PRs merged since 2026-04-25** (up from 39 at the original scorecard's measurement; up from ~50 at the morning refresh).

PR-type breakdown (rough):
- `refactor:` ~25 (monolith extractions)
- `fix:` ~6 (bugs caught + fixed during extraction)
- `feat:` ~3
- `test:` ~5
- `docs:` ~25 (handoffs + sync docs + plan amendments)
- `handoff(...):` ~10 (new convention from PR #67)
- `chore:` ~1

Queue-prompt-noise subset (the historical pattern that PR #67 deprecated): ~7 in the early hours, dropped to near-zero after the new handoff convention took hold.

---

## 5. Coordination state — what's now in place

Process scaffolding that didn't exist at the original scorecard:

- ✓ Phase 0 baseline signed (PR #64)
- ✓ AGENTS.md repo-target rule (PR #74) — prevents the wrong-repo trap that hit PRs #225, #226, #229
- ✓ Handoff convention `.hermes/handoffs/<agent>/` (PR #67)
- ✓ Screenshot link convention (PR #89) — fixes the silent-404 issue on private repo
- ✓ Coordinator sync doc (PR #96) — single source of truth for state
- ✓ Option 3 cancelled (PR #98) — scope locked to Option 1 only
- ✓ Oracle bug-sync authorized (PR #99) — path-separator + TranscriptionLanes fixes will land on oracle
- ✓ Parity inventory §11 Accepted oracle deviations (PR #96)
- ✓ Parity inventory §12 Current evidence priority (PR #96)
- ✓ Phase 0 baseline status note (PR #96) — clarifies frozen vs current SHAs
- ✓ Wait-rule discipline relaxed (PR #93 + #99) — agents proven to handle repo discipline without per-PR gates

Process gaps still open:

- ❌ Worktree pruning (~40 worktrees on disk; deferred from multiple handoffs)
- ❌ Auto-* lanes restart (deferred — coordinator-driven cadence working well per Lucas decision in PR #96)
- ❌ Oracle 10 failing backend tests classification (long-deferred audit)

---

## 6. Open decisions for Lucas (carryover from PR #96 sync)

- ✅ **Option 3 cancellation** — DECIDED via PR #98 (cancelled)
- ✅ **Oracle sync PRs** — DECIDED, parse-gpt authorized via PR #99 (path-separator + TranscriptionLanes hook-order)
- ✅ **Repo visibility** — DECIDED, no flip
- ✅ **Auto-* lanes** — DECIDED, keep coordinator-driven for now

All 5 PR #96 decisions resolved.

---

## 7. Recommended next 3 priorities

In order:

1. **parse-gpt drains the merge tail** — 10 PRs open (95-104), all mergeable (95 needs rebase first). Bottleneck is parse-gpt scheduling, not work itself.
2. **Tags parity evidence pass** (parse-gpt PR #103) — twice-deferred P0 surface. After this ships, parity coverage hits 37.5%.
3. **chat_tools PR 3A implementation** (parse-back-end, per PR #100 pre-research) — tag_import_tools.py + memory_tools.py, ~600 LoC. Drops chat_tools.py toward 4250.

After those: chat_tools PR 3B/3C, mcp_adapter PR 1 (env_config.py per PR #102), TranscriptionLanes PR C/D, BatchReportModal decomposition (PR #101), AI/chat parity.

---

## 8. Definition of "Option 1 done"

Concrete completion criteria for the rebuild's scope-locked end state:

| Gate | Target | Current | Status |
|---|---|---:|---|
| ParseUI.tsx | ≤1800 LoC | 2035 | near (TranscriptionLanes/BatchReportModal extractions will close gap by sibling reduction) |
| chat_tools.py | ≤2500 LoC (PR #59 goal) | 4850 | PRs 3 + 4 queued, will hit |
| server.py | ≤5000 LoC (suggested target) | 7757 | needs more HTTP handler passes; not scoped yet |
| mcp_adapter.py | ≤1000 LoC (5-module decomposition) | 2050 | PR 1 queued via #102, PRs 2-5 future |
| provider.py | TBD (audit needed first) | 1907 | future |
| All 3 P0 parity surfaces shipped | Annotate + Compare + Tags | 2/3 (Tags mandatory next) | PR #103 |
| All 5 P1 parity surfaces shipped | AI/chat + Import + Compute + CLEF + Jobs | 0/5 | future handoffs |
| All accepted oracle deviations resolved or sync'd | path-separator + hook-order + 10 failing tests | 2 sync'd (PR #99); 10 unclassified | partial |
| Test files | (no specific gate) | 144 (59 frontend + 85 backend) | continually growing |

**Estimated time to Option 1 done at current pace:** 3-5 days of similar coordinator-driven cadence. Parity work is the bottleneck more than monolith reduction.
