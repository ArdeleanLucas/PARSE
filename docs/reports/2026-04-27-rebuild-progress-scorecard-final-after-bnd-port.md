# PARSE-rebuild progress scorecard — final BND-wave coordinator closeout

This scorecard supersedes the earlier 2026-04-27 draft/final-v2 snapshots for the BND/MCP port wave.

## TL;DR

- **BND frontend scope:** landed via PR #149; investigation verdict `A` confirms it is the real frontend port
- **BND backend/MCP scope:** landed via PR #152
- **Current BND feature-contract diff count:** `0`
- **Full harness status:** `raw 9 / allowlisted 9 / unallowlisted 0`
- **Meaning of the remaining raw entries:** 8 metadata-only MCP descriptor-copy diffs plus 1 accepted oracle-only boot quirk
- **Cutover verdict:** `needs-fixes` because PR #159 still reports real-workspace dogfood failures (#143 and #154). Harness parity is no longer the blocker.

## Current main snapshot

- **Oracle SHA:** `b34578b45f2b972f7a04d44939069ad5684e461c`
- **Rebuild SHA:** `fdd9af7625d349e8c40f47513155f7f135f222bf`
- **Audit fixture:** `saha-2speaker`
- **PR #149 verdict:** `A` — `docs/reports/2026-04-27-pr149-scope-investigation.md`
- **Merged BND frontend PR:** https://github.com/TarahAssistant/PARSE-rebuild/pull/149
- **Merged BND backend PR:** https://github.com/TarahAssistant/PARSE-rebuild/pull/152
- **Dogfood blocker PR/report:** https://github.com/TarahAssistant/PARSE-rebuild/pull/159 / `docs/reports/2026-04-27-rebuild-dogfood-post-fix-verification.md`

## Final coordinator harness snapshot

### Standard full harness (`all` sections)
- raw diff count: **9**
- allowlist count: **9**
- unallowlisted count: **0**
- section mix: `mcp_tools=8`, `server_boot_smoke=1`

### BND feature-contract harness slice
- raw diff count: **0**
- allowlist count: **0**
- unallowlisted count: **0**
- previous coordinator checkpoint before PR #149/#152 were merged: **16**

### MCP + boot triage breakdown
- **mcp_tools:** `0` real rebuild gaps / `32` harness-artifact diffs closed by fresh MCP-fixture isolation / `8` metadata-only diffs allowlisted
- **server_boot_smoke:** `0` rebuild gaps / local port-collision artifact removed by isolated boot ports / `1` oracle-only boot failure allowlisted as accepted baseline deviation

## Validation evidence

- `PYTHONPATH=. python3 -m pytest parity/harness/tests -q` → `21 passed`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --diff-category feature_contracts --output-dir /tmp/parse-bnd-fc-refreshed` → `raw 0`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --diff-category mcp_tools --output-dir /tmp/parse-bnd-mcp-allowlisted` → `raw 8 / allowlisted 8 / unallowlisted 0`
- `PYTHONPATH=. python3 -m parity.harness.runner --oracle /home/lucas/gh/ardeleanlucas/parse --rebuild . --fixture saha-2speaker --emit-signoff --output-dir /tmp/parse-bnd-full-final-v3` → `raw 9 / allowlisted 9 / unallowlisted 0`
- `npx vitest run` → `431 passed`
- `./node_modules/.bin/tsc --noEmit` → clean
- `PYTHONPATH=. python3 -m pytest -q -k 'not test_ortho_section_defaults_cascade_guard and not test_ortho_explicit_override_beats_defaults' python` → `777 passed, 2 deselected`

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

| Cluster | Rebuild LoC | File count | Status |
|---|---:|---:|---|
| CLEF cluster | 1,320 | 13 | carry-forward baseline (not refreshed in this coordinator-only closeout) |
| Compare cluster | 4,516 | 38 | carry-forward baseline (not refreshed in this coordinator-only closeout) |
| Annotate cluster | 6,725 | 47 | carry-forward baseline (not refreshed in this coordinator-only closeout) |
| Hooks cluster | 5,174 | 40 | carry-forward baseline (not refreshed in this coordinator-only closeout) |

## P0 / P1 surface coverage snapshot

| Surface | Priority | Current status | Notes |
|---|---|---|---|
| Shell / navigation | P0 | `blocked-by-dogfood` | PR #159 still reports live thesis-workspace failures. |
| Annotate core | P0 | `blocked-by-dogfood` | Save → reload regression (#143) still fails in real-workspace dogfood. |
| Compare core | P0 | `blocked-by-dogfood` | Final browser verdict still depends on the same real-workspace lane. |
| Annotate BND / phonetic-tools UI | P0 | `pass-via-harness` | PR #149 merged; refreshed source-audit now matches rebuild literals. |
| BND UI gate surfaces (`tiers.ortho_words`, STT word timestamps) | P0 | `pass-via-harness` | Gate logic verified via `bndIntervalCount` and `sttHasWordTimestamps` rather than stale oracle-only headings. |
| BND / MCP backend surface | P1 | `pass-via-harness` | PR #152 merged; only metadata-copy diffs remain and are explicitly allowlisted. |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | Historical browser evidence remains authoritative here. |
| Import / onboarding | P1 | `pass-via-harness` | Shared harness coverage remains green. |
| Compute and report modals | P1 | `blocked-by-dogfood` | Browser-side persistence/UX still waits on the real-workspace lane. |
| Contact lexeme / CLEF compare extensions | P1 | `pass-via-harness` | Harness covers CLEF config/catalog/providers/report plus contact-lexeme jobs. |
| Job diagnostics | P1 | `pass-via-harness` | Harness covers `/api/jobs`, `/api/jobs/active`, and `/api/jobs/{jobId}/logs`. |
| ~~AI/chat shell~~ | P1 | `dropped` | Out of scope. |

## Current coordinator recommendation

Do **not** queue parse-front-end on a fresh BND/UI implementation task. That work already landed in PR #149. Do **not** hold cutover for coordinator parity work any longer either: the harness is now clean on all unallowlisted diffs. The remaining blocker is the real-workspace dogfood lane in PR #159, which still records:
1. #143 save/reload regression still failing
2. #154 note persistence still failing without blur on reload
3. #153 did not reproduce in the focused re-verification pass

## Final verdict

- **Coordinator parity verdict:** `PASS`
- **Cutover-readiness verdict:** `needs-fixes`
- **Reason:** rebuild is caught up through oracle PR #242 for coordinator-owned parity/harness surfaces, but live thesis-workspace dogfood still reports user-visible regressions. Merge this coordinator PR as the final parity record, then hold cutover until PR #159 is resolved or superseded by a passing dogfood artifact.
