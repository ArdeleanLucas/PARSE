# PARSE-rebuild progress scorecard — 2026-04-26 late refresh

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


**Date:** 2026-04-26
**Measurement timestamp (UTC):** `2026-04-26T21:10:00Z`
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`
**Rebuild SHA (current main at measurement):** `9dd8cc7d012a38d7e697a4ba0822e0e885da19e1`
**Oracle repo:** `ArdeleanLucas/PARSE`
**Oracle SHA (frozen baseline):** `0951287a812609068933ba22711a8ecd97765f38`
**Supersedes:** `docs/reports/2026-04-26-rebuild-progress-scorecard-evening-refresh.md`

---

## TL;DR

- `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) is now **3192 LoC** on rebuild `origin/main`.
- `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) remains **2050 LoC** and untouched.
- The next parse-back-end execution sequence is now explicit:
  1. **chat_tools PR 4 pre-research docs PR**
  2. **chat_tools PR 4 implementation PR**
  3. **mcp_adapter PR 1 (`env_config.py`)**
- Reason the first PR is docs-only: PR #102 gives the governing grouped-domain spec, but not grounded current line ranges / family-size estimates for the PR 4 extraction.

---

## 1) Pressure-monolith snapshot on current `origin/main`

| File | Current rebuild LoC | State |
|---|---:|---|
| `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) | 7757 | still the largest backend monolith |
| `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) | 3192 | materially reduced; final extraction wave still queued |
| `src/ParseUI.tsx` | 2035 | already structurally cracked |
| `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) | 2050 | untouched; PR 1 seam queued |
| `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`) | 1907 | untouched |

Interpretation: the chat-tools reduction wave has moved far enough that the remaining backend structural priority is now the **final chat_tools extraction map** and then the **first MCP adapter seam**.

---

## 2) Live open-PR queue snapshot

Grounded with `git fetch origin --quiet --prune` + `gh pr list`.

| PR | Title | Merge state |
|---|---|---|
| `#121` | `docs(coordinator): 2026-04-26 session end snapshot — pick-up-cold handoff` | `CLEAN` |
| `#112` | `refactor(batch-report): extract table row` | `DIRTY` |
| `#107` | `refactor(annotate): extract inline edit controller from TranscriptionLanes.tsx` | `DIRTY` |

Interpretation: no open backend implementation PR currently occupies the parse-back-end lane, so the next backend execution unit can be handed off directly.

---

## 3) Backend sequencing checkpoint

### Governing spec

- PR #102 remains the authoritative scope/order doc for the lane:
  - chat_tools PR 4
  - then mcp_adapter PR 1 (`env_config.py`)

### New coordinator decision

The first parse-back-end PR is **not** the PR 4 implementation directly.
It is the **PR 4 pre-research docs PR**, because the user-added gate requires a grounded pre-research pass whenever a `>500`-LoC target lacks current line ranges + LoC estimates in the governing spec.

### First PR to open

`docs(chat_tools): PR 4 pre-research for compare/enrichment/export bundles`

Expected product of that PR:
- current exact line map in `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`)
- current family-size estimates
- grouped-module extraction recommendation for:
  - `compare_tools.py`
  - `enrichment_tools.py`
  - `export_tools.py`
- implementation test map

---

## 4) Guardrails for the backend lane

- All PR creation commands must use `--repo TarahAssistant/PARSE-rebuild`
- Always run `git fetch origin --quiet --prune` immediately before any mergeability claim
- Screenshot references must be links, not embeds
- MC item + daily log + scorecard update are required after **each** PR in the lane

---

## 5) Immediate coordinator recommendation

Signal parse-back-end now with a go handoff that points at PR #102, explicitly names the first PR as the pre-research docs slice, and leaves the later `mcp_adapter` PR 1 on deck after chat_tools PR 4 lands.
