# PARSE-rebuild progress scorecard — final BND-wave signoff prep (DRAFT)

> **DRAFT — landing after coordinator harness refresh + final real-workspace dogfood rerun.**
> This scorecard supersedes the earlier 2026-04-27 final-v2 scorecard once the BND-wave closeout is actually ready to merge.

## TL;DR

- **BND frontend scope:** landed via PR #149; investigation verdict `A` confirms it is the real frontend port
- **BND backend/MCP scope:** landed via PR #152
- **Current BND feature-contract diff count:** `4` (down from the earlier `16`)
- **Meaning of the remaining 4 diffs:** stale coordinator source-audit exact-string mismatches, not missing frontend/backend BND code
- **Cutover still blocked today by:**
  1. coordinator harness refresh + final rerun
  2. parse-front-end real-workspace dogfood gate

## Current main snapshot

- **Oracle SHA:** `b34578b45f2b972f7a04d44939069ad5684e461c`
- **Rebuild SHA:** `6a55178da264794a60d1f2de32fc9daab9baef94`
- **Audit fixture:** `saha-2speaker`
- **PR #149 verdict:** `A` — `docs/reports/2026-04-27-pr149-scope-investigation.md`
- **Merged BND frontend PR:** https://github.com/TarahAssistant/PARSE-rebuild/pull/149
- **Merged BND backend PR:** https://github.com/TarahAssistant/PARSE-rebuild/pull/152

## Pre-flight harness snapshot at draft creation

### Standard full harness (`all` sections)
- raw diff count: **42**
- allowlist count: **0**
- unallowed count: **42**
- section mix: `mcp_tools=40`, `server_boot_smoke=2`

### BND feature-contract harness slice
- raw diff count: **4**
- allowlist count: **0**
- unallowed count: **4**
- previous coordinator checkpoint before PR #149/#152 were merged: **16**

### Expected closeout path
The remaining BND-related `4` diffs should close after a coordinator harness refresh/rerun that stops treating these oracle-only literals as required rebuild strings:
- exact frontend heading literal `Phonetic Tools`
- exact backend string form `ortho_source = "ortho_words"`

## Monolith state snapshot

| File | Oracle LoC | Rebuild LoC | Delta | Delta % |
|---|---:|---:|---:|---:|
| `python/server.py` | 9,294 | 1,999 | -7,295 | -78.5% |
| `python/ai/chat_tools.py` | 6,692 | 1,342 | -5,350 | -80.0% |
| `src/ParseUI.tsx` | 5,533 | 2,180 | -3,353 | -60.6% |
| `python/adapters/mcp_adapter.py` | 2,151 | 218 | -1,933 | -89.9% |
| `python/ai/provider.py` | 2,049 | 325 | -1,724 | -84.1% |
| `src/api/client.ts` | 1,048 | 18 | -1,030 | -98.3% |
| `src/stores/annotationStore.ts` | 753 | 23 | -730 | -96.9% |
| `src/components/shared/BatchReportModal.tsx` | 843 | 174 | -669 | -79.4% |
| `src/components/shared/TranscriptionRunModal.tsx` | 792 | 298 | -494 | -62.4% |
| `src/components/annotate/TranscriptionLanes.tsx` | 973 | 623 | -350 | -36.0% |

## Cluster-decomposition totals

> Carry-forward baseline from `docs/reports/2026-04-27-rebuild-progress-scorecard-final-v2.md`; refresh on final landing.

| Cluster | Rebuild LoC | File count | Status |
|---|---:|---:|---|
| CLEF cluster | 1,320 | 13 | carry-forward baseline `<!-- TBD refresh on landing -->` |
| Compare cluster | 4,516 | 38 | carry-forward baseline `<!-- TBD refresh on landing -->` |
| Annotate cluster | 6,725 | 47 | carry-forward baseline `<!-- TBD refresh on landing -->` |
| Hooks cluster | 5,174 | 40 | carry-forward baseline `<!-- TBD refresh on landing -->` |

## P0 / P1 surface coverage snapshot

| Surface | Priority | Current status | Notes |
|---|---|---|---|
| Shell / navigation | P0 | `blocked` | Fresh real-workspace dogfood rerun still pending. |
| Annotate core | P0 | `blocked` | Fresh real-workspace dogfood rerun still pending. |
| Compare core | P0 | `blocked` | Fresh real-workspace dogfood rerun still pending. |
| Annotate BND / phonetic-tools UI | P0 | `ported-awaiting-final-rerun` | PR #149 merged; buttons + gates are present on main. |
| BND UI gate surfaces (`tiers.ortho_words`, STT word timestamps) | P0 | `ported-awaiting-final-rerun` | PR #149 merged; current remaining diff is harness exact-string mismatch, not missing UI logic. |
| BND / MCP backend surface | P1 | `ported-awaiting-final-rerun` | PR #152 merged; compute routing + chat/MCP exposure are present on main. |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | Historical browser evidence still exists; no new BND-specific blocker here. |
| Import / onboarding | P1 | `pass-via-harness` | Underlying shared harness coverage remains present. |
| Compute and report modals | P1 | `blocked` | Final browser rerun still pending. |
| Contact lexeme / CLEF compare extensions | P1 | `blocked` | Final browser rerun still pending. |
| Job diagnostics | P1 | `pass-via-harness` | Underlying shared harness coverage remains present. |
| ~~AI/chat shell~~ | P1 | `dropped` | Out of scope. |

## Post-landing placeholders

- **Final full-harness raw diff count:** `<!-- TBD post coordinator harness refresh + final rerun -->`
- **Final feature-contract diff count:** `<!-- TBD post coordinator harness refresh + final rerun -->`
- **Final dogfood result:** `<!-- TBD post parse-front-end real-workspace rerun -->`
- **Final cutover-readiness verdict:** `<!-- TBD once both lines above are complete -->`

## Current coordinator recommendation

Do **not** queue parse-front-end on a fresh BND/UI implementation task. The frontend BND port is already landed in PR #149. The next coordinator actions are:
1. refresh the BND `feature_contracts` audit rules so current-main reruns cleanly
2. merge the real-workspace dogfood evidence once parse-front-end finishes that lane
