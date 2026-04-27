# PARSE-rebuild progress scorecard — final Option 1 sign-off audit v2

> Supersedes `docs/reports/2026-04-27-rebuild-progress-scorecard-final.md` and the blocker-focused audit shipped in PR #141.

## TL;DR

- **Browser/workstation rebuild progress:** strong structural state; backend/data/export parity meta-gate is now clean
- **Parity meta-gate:** `raw=0`, `allowlisted=0`, `unallowed=0`
- **Operational blocker count:** **0**
- **Desktop distribution readiness:** still out of scope for this audit (Option 3 cancelled)

## Current main snapshot

- **Oracle SHA:** `c2fb743fbb30119bfcd18ce9d802f3125449acdf`
- **Rebuild SHA:** `a1ab21176adcd6cbdcb3e96905f8370cd03e6e7d`
- **Audit fixture:** `saha-2speaker`
- **Server boot smoke:** oracle `PASS`, rebuild `PASS`

## What changed since PR #141's audit

- PR **#139** (`fix(server): restore script-mode bootstrap`) merged to rebuild `origin/main`.
- The same Round 3 harness invocation was rerun on fresh current-main.
- The only prior blocker (`$.server_boot_smoke.rebuild`) disappeared.
- Current parity output is now fully clean: no raw diffs, no allowlisted diffs, no unallowlisted diffs.

## Fresh audit result

Command:
```bash
PYTHONPATH=. python -m parity.harness.runner   --oracle /home/lucas/gh/ardeleanlucas/parse   --rebuild .   --fixture saha-2speaker   --emit-signoff   --output-dir /tmp/parse-option1-signoff-audit-v2   --keep-temp
```

Result:
- raw diff count: **0**
- allowlist count: **0**
- unallowed count: **0**
- server boot smoke: **PASS** on both repos

## Monolith state snapshot

| File | Oracle LoC | Rebuild LoC | Delta | Delta % |
|---|---:|---:|---:|---:|
| `python/server.py` | 8,972 | 1,978 | -6,994 | -78.0% |
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

At the **parity meta-gate / backend operational** level, the rebuild is now ready to replace the oracle: the shared harness is clean and the script-mode server boot now matches oracle behavior. Remaining blocked rows are browser-workbench parity closure items that still need explicit browser evidence before claiming total end-to-end workstation sign-off across every P0/P1 surface.
