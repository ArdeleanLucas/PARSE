# PARSE-rebuild progress scorecard — final Option 1 sign-off audit

> Supersedes `docs/reports/2026-04-26-rebuild-progress-scorecard-evening-refresh.md` and later same-day refresh notes.

## TL;DR

- **Browser/workstation rebuild progress:** strong structural state, but **not yet Option 1 sign-off ready**
- **Parity meta-gate:** in place and working (`raw=1`, `allowlisted=0`, `unallowed=1`)
- **Operational blocker count:** **1**
- **Desktop distribution readiness:** still out of scope for this audit (Option 3 cancelled)

## Current main snapshot

- **Oracle SHA:** `c2fb743fbb30119bfcd18ce9d802f3125449acdf`
- **Rebuild SHA:** `7986f5d95771015bed1f00bca262d9317f3b501f`
- **Round 3 audit fixture:** `saha-2speaker`
- **Server boot smoke:** oracle `PASS`, rebuild `FAIL`

## What improved since the 2026-04-26 refreshes

- The shared parity harness now covers every §6 contract group in one reproducible runner.
- LingPy + NEXUS export parity is captured inside the harness with a cognate-decision fixture state.
- Required failure modes are covered in one artifact instead of being spread across ad-hoc notes.
- Script-mode boot now has an explicit meta-gate, which prevents a misleading `0-diff` report when the rebuild cannot actually boot `python/server.py` the same way the oracle does.

## Why Option 1 is not fully signed off yet

| Blocker | Severity | Current state | Resolution path |
|---|---|---|---|
| Rebuild direct script boot (`python python/server.py`) | High | **FAIL** on current `origin/main` with `NameError: _api_get_annotation is not defined` | Expected to resolve when PR **#137** lands |

## Monolith state snapshot

| File | Oracle LoC | Rebuild LoC | Delta | Delta % |
|---|---:|---:|---:|---:|
| `python/server.py` | 8,972 | 1,910 | -7,062 | -78.7% |
| `python/ai/chat_tools.py` | 6,408 | 1,273 | -5,135 | -80.1% |
| `src/ParseUI.tsx` | 5,328 | 2,035 | -3,293 | -61.8% |
| `python/adapters/mcp_adapter.py` | 2,050 | 218 | -1,832 | -89.4% |
| `python/ai/provider.py` | 1,907 | 325 | -1,582 | -83.0% |
| `src/api/client.ts` | 1,048 | 18 | -1,030 | -98.3% |
| `src/stores/annotationStore.ts` | 753 | 23 | -730 | -96.9% |
| `src/components/shared/BatchReportModal.tsx` | 843 | 174 | -669 | -79.4% |
| `src/components/shared/TranscriptionRunModal.tsx` | 792 | 298 | -494 | -62.4% |
| `src/components/annotate/TranscriptionLanes.tsx` | 943 | 613 | -330 | -35.0% |

### Cluster totals on rebuild current-main

| Cluster | Rebuild LoC | File count |
|---|---:|---:|
| CLEF cluster | 1,320 | 13 |
| Compare cluster | 4,516 | 38 |
| Annotate cluster | 6,725 | 47 |
| Hooks cluster | 5,174 | 40 |

## Surface closure summary

| Surface | Priority | Status |
|---|---|---|
| Shell / navigation | P0 | blocked |
| Annotate | P0 | blocked |
| Compare | P0 | blocked |
| Tags / enrichments management | P0 | pass-via-evidence-doc |
| Import / onboarding | P1 | pass-via-harness |
| Compute and report modals | P1 | blocked |
| Contact lexeme / CLEF compare extensions | P1 | pass-via-harness |
| Job diagnostics | P1 | pass-via-harness |
| AI/chat shell | P1 | dropped |

## Readiness call

The rebuild is **near-done, not ready**. The structural monolith-reduction work is substantial and the contract-level parity harness is now credible, but the remaining script-boot failure is a release-signoff blocker because it means rebuild `origin/main` still cannot replace the oracle in the exact `python/server.py` invocation path.
