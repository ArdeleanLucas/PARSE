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
| Shell / navigation | P0 | `blocked` | `docs/reports/2026-04-27-rebuild-dogfood-report.md` | Real-workspace dogfood found a frontend process kill during Annotate load (#153). |
| Annotate | P0 | `blocked` | `docs/reports/2026-04-27-rebuild-dogfood-report.md` | Real-workspace dogfood found non-persistent Annotate save behavior (#143) and runtime instability (#153). |
| Compare | P0 | `blocked` | `docs/reports/2026-04-27-rebuild-dogfood-report.md` | Compare notes did not persist across reload in the real workspace dogfood pass (#154). |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | `docs/reports/2026-04-26-tags-parity-evidence.md` | Browser Tags parity previously passed `7/7` flows; the shared harness also covers the underlying contracts. |
| ~~AI/chat shell~~ | P1 | `dropped` | scope decision | Dropped from rebuild parity scope on 2026-04-26. |
| Import / onboarding | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers concept/tag import, onboard start/poll, persistence, and required error envelopes. |
| Compute and report modals | P1 | `blocked` | `docs/reports/2026-04-27-rebuild-dogfood-report.md` | CLEF populate completed with zero fetched reference forms during real-workspace dogfood (#155). |
| Contact lexeme / CLEF compare extensions | P1 | `blocked` | `docs/reports/2026-04-27-rebuild-dogfood-report.md` | Harness covers contracts, but real-workspace dogfood exposed a zero-result populate outcome that still needs thesis-facing validation (#155). |
| Job diagnostics | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers `/api/jobs`, `/api/jobs/active`, and `/api/jobs/{jobId}/logs`. |

## Real-blocker diffs

- #143 — Annotate save does not persist IPA / orthography field edits after reload.
- #153 — Frontend dev server is killed during real-workspace Annotate load.
- #154 — Compare notes are not persisted across reload.
- #155 — CLEF populate can complete with zero fetched reference forms.

## Option 1 readiness

**Not ready to replace oracle for thesis-facing use yet.**

The parity/meta-gate harness remains green (`raw=0`, `allowlisted=0`, `unallowed=0`), but the real-workspace browser dogfood pass uncovered blocker-class user-facing failures in Annotate runtime stability and save persistence, plus additional Compare/CLEF regressions. Option 1 therefore remains blocked on the filed dogfood issues even though the lower-level parity harness is currently clean.

## Dogfood follow-up

- **Dogfood pass (real workspace):** 9 flows tested, 4 issues filed, 2 blockers. Report: `docs/reports/2026-04-27-rebuild-dogfood-report.md`. Issue links: #143, #153, #154, #155.

## Coordinator sign-off

- **Lucas:** ______________________________
- **Date:** ______________________________
- **Decision:** `blocked pending dogfood fixes`
