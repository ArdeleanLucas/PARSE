> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# PARSE-rebuild progress scorecard — 2026-04-26 evening refresh

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


**Date:** 2026-04-26
**Measurement timestamp (UTC):** `2026-04-26T19:23:08Z`
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`
**Rebuild SHA (current main at measurement):** `cdb316ca4b739b0ad496f1b58a50a7a3f2082cb4`
**Oracle repo:** `ArdeleanLucas/PARSE`
**Oracle SHA (frozen baseline):** `0951287a812609068933ba22711a8ecd97765f38`
**Supersedes:** `docs/reports/2026-04-26-rebuild-progress-scorecard.md`

---

## TL;DR

- **Monolith reduction:** substantial progress (**6,066 LoC removed / 24,665 = 24.6%**) across the pressure set.
- **Largest win:** `src/ParseUI.tsx` is now **2,035 LoC** (from oracle **5,328**, a **61.8% reduction**).
- **Backend movement:** `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) is now **4,850 LoC** (from oracle **6,408**, a **24.3% reduction**).
- **Parity evidence:** **2/4 P0 surfaces** now have committed evidence on `main` (Annotate + Compare).
- **Desktop axis:** **N/A / cancelled** in this rebuild lane (Option 3 cancelled by PR #98).

---

## 1) Monolith reduction (grounded on current `origin/main`)

| File | Oracle LoC | Rebuild LoC | Delta | Delta % | Status |
|---|---:|---:|---:|---:|---|
| `src/ParseUI.tsx` | 5,328 | **2,035** | **-3,293** | **-61.8%** | structurally cracked; remaining reductions moved to sibling files |
| `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) | 6,408 | **4,850** | **-1,558** | **-24.3%** | in progress; PR 3 flow active, PR 4 queued |
| `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) | 8,972 | **7,757** | **-1,215** | **-13.5%** | in progress |
| `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) | 2,050 | **2,050** | 0 | 0.0% | untouched; PR 1 seam queued (`env_config.py`) |
| `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`) | 1,907 | **1,907** | 0 | 0.0% | untouched |
| **Total** | **24,665** | **18,599** | **-6,066** | **-24.6%** | |

Interpretation: reduction is real and now broad enough to be visible outside ParseUI, but two backend monoliths (`mcp_adapter.py`, `provider.py`) remain untouched on `main`.

---

## 2) Parity-evidence coverage (P0 surfaces)

| P0 surface (`option1-parity-inventory.md` §5.1) | Evidence on `main`? | Evidence path / PR | State |
|---|---|---|---|
| Shell / navigation | No | none yet | pending |
| Annotate | Yes | `docs/reports/2026-04-26-annotate-parity-evidence.md` (PR #66) | shipped |
| Compare | Yes | `docs/reports/2026-04-26-compare-parity-evidence.md` (PR #87) | shipped |
| Tags / enrichments management | No (in progress) | open PR #103 | mandatory next |

**Coverage:** `2/4` P0 surfaces (50%).

---

## 3) Desktop-distribution readiness axis

**Status:** **de-scoped / cancelled for this rebuild lane**.

- PR #98 cancelled Option 3 (desktop platform pivot).
- `AGENTS.md` now declares **Scope: Option 1 only**.
- Desktop architecture/checklist docs are retained as historical context, not active rebuild gates.

---

## 4) Velocity snapshot (last 24h window)

Window: `2026-04-25T19:23:08Z` → `2026-04-26T19:23:08Z`

- **Merged PRs:** `75`
- **Open PRs at measurement:** `7`
- **Merged PR type breakdown (prefix-based):**
  - `refactor:` 26
  - `feat:` 2
  - `fix:` 7
  - `docs:` 23
  - `test:` 3
  - `chore:` 0
  - `other:` 14 (includes handoff-style titles without standard prefix)
- **Legacy queue-prompt docs subset (`docs: queue ...`) merged in window:** `3`

Interpretation: throughput remains very high; the newer `.hermes/handoffs/` convention is reducing legacy queue-prompt PR noise.

---

## 5) Coordination state (live open PR queue)

Current open PRs (grounded via `gh pr list`, same measurement window):

- **#106** `docs(coordinator): scorecard refresh — evening 2026-04-26` — `CLEAN`
- **#105** `refactor(annotate): extract boundary edit affordance from TranscriptionLanes.tsx` — `CLEAN` (stacked on #104)
- **#104** `refactor(annotate): extract lane action toolbar from TranscriptionLanes.tsx` — `DIRTY`
- **#103** `handoff(parse-gpt): Tags parity (MANDATORY) + scorecard + cleanup` — `CLEAN`
- **#102** `handoff(parse-back-end): chat_tools PR 4 + mcp_adapter PR 1 (env_config.py)` — `CLEAN`
- **#101** `handoff(parse-builder): BatchReportModal.tsx decomposition` — `CLEAN`
- **#95** `[MC-326] fix(chat_tools): normalize stt_start sourceWav payload` — `DIRTY`

Coordinator checkpoints:

- Phase 0 baseline signed: **YES** (PR #64 merged)
- Option 3 cancelled / scope locked to Option 1: **YES** (PR #98 merged)
- Oracle sync authorization for path-separator + hook-order fixes: **YES** (PR #99 merged)
- Parse-back-end `mcp_adapter` PR1 handoff queued: **YES** (PR #102 open)
- Tags parity evidence shipped: **NO** (still queued in PR #103)

---

## 6) Recommended immediate coordinator sequence

1. Keep draining clean coordinator/handoff PRs (`#101`, `#102`, `#103`, `#106`) while preserving task ordering constraints.
2. Rebase/unstick dirty implementation PRs (`#95`, `#104`) to unblock stack flow.
3. Treat Tags parity publication as the next parity gate completion (PR #103), then promote AI/chat parity to top remaining evidence priority.
