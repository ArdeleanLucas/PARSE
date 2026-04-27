# PARSE Option 1 sign-off audit — 2026-04-27 (post-PR #139 refresh)

## Audit snapshot

- **Oracle repo / SHA:** `ArdeleanLucas/PARSE` @ `c2fb743fbb30119bfcd18ce9d802f3125449acdf`
- **Rebuild repo / SHA:** `TarahAssistant/PARSE-rebuild` @ `a1ab21176adcd6cbdcb3e96905f8370cd03e6e7d`
- **Harness fixture:** `saha-2speaker`
- **Harness raw diff count:** `0`
- **Harness allowlist count:** `0`
- **Harness unallowed count:** `0`
- **Allowlist reasons:** none — `parity/harness/allowlist.yaml` is empty at audit time

## Server-boot smoke check

| Repo | Result | Detail | Evidence |
|---|---|---|---|
| Oracle | PASS | Booted on port 8766. | `/tmp/parse-option1-signoff-audit-v2/oracle-server-script.log` |
| Rebuild | PASS | Booted on port 8766. | `/tmp/parse-option1-signoff-audit-v2/rebuild-server-script.log` |

## Monolith state snapshot

### Originally tracked pressure files

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

### Cluster-decomposition totals (rebuild current-main)

| Cluster | Rebuild LoC | File count |
|---|---:|---:|
| CLEF cluster | 1,320 | 13 |
| Compare cluster | 4,516 | 38 |
| Annotate cluster | 6,725 | 47 |
| Hooks cluster | 5,174 | 40 |

## P0 / P1 surface coverage matrix

| Surface | Priority | Status | Evidence route | Notes |
|---|---|---|---|---|
| Shell / navigation | P0 | `blocked` | none yet | Current harness proves backend/data/export parity, but no final post-merge shell-navigation browser audit has been rerun on current `origin/main`. |
| Annotate | P0 | `blocked` | `docs/reports/2026-04-26-annotate-parity-evidence.md` | Historical evidence captured the pre-`#234` oracle-side crash; a fresh rerun is still needed before claiming browser parity closure. |
| Compare | P0 | `blocked` | `docs/reports/2026-04-26-compare-parity-evidence.md` | Historical evidence still records decision-row `Accept / Split / Merge` divergence on rebuild current-main. |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | `docs/reports/2026-04-26-tags-parity-evidence.md` | Browser Tags parity passed `7/7` flows; the shared harness also covers the underlying contracts. |
| ~~AI/chat shell~~ | P1 | `dropped` | scope decision | Dropped from rebuild parity scope on 2026-04-26. |
| Import / onboarding | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers concept/tag import, onboard start/poll, persistence, and required error envelopes. |
| Compute and report modals | P1 | `blocked` | partial harness coverage | Harness covers the underlying compute/report contracts, but the modal/browser affordances themselves have not been rerun as a final browser parity pass. |
| Contact lexeme / CLEF compare extensions | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers CLEF config/catalog/providers/report plus contact-lexeme coverage and fetch lifecycles. |
| Job diagnostics | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers `/api/jobs`, `/api/jobs/active`, and `/api/jobs/{jobId}/logs`. |

## Real-blocker diffs

**none — Option 1 ready**

## Option 1 readiness

**Ready to replace oracle at the parity/meta-gate level.** The harness now reports `raw=0`, `allowlisted=0`, `unallowed=0`, and the direct script-mode `python python/server.py` smoke passes on both oracle and rebuild current-main.

## Dogfood follow-up

- **Dogfood pass (Fail01):** 13 flows tested, 1 issues filed, 0 blockers. Report: `docs/reports/2026-04-27-rebuild-dogfood-report.md`. Issue links: #143.

## Coordinator sign-off

- **Lucas:** ______________________________
- **Date:** ______________________________
- **Decision:** `ready`
