# PARSE Option 1 sign-off audit — 2026-04-27

## Audit snapshot

- **Oracle repo / SHA:** `ArdeleanLucas/PARSE` @ `c2fb743fbb30119bfcd18ce9d802f3125449acdf`
- **Rebuild repo / SHA:** `TarahAssistant/PARSE-rebuild` @ `7986f5d95771015bed1f00bca262d9317f3b501f`
- **Harness fixture:** `saha-2speaker`
- **Harness raw diff count:** `1`
- **Harness allowlist count:** `0`
- **Harness unallowed count:** `1`
- **Allowlist reasons:** none — `parity/harness/allowlist.yaml` is empty at audit time

## Server-boot smoke check

| Repo | Result | Detail | Evidence |
|---|---|---|---|
| Oracle | PASS | Booted on port 8766. | `/tmp/parse-option1-signoff-audit/oracle-server-script.log` |
| Rebuild | FAIL | `NameError: _api_get_annotation is not defined` during direct `python python/server.py` boot on current `origin/main` | `/tmp/parse-option1-signoff-audit/rebuild-server-script.log` |

## Monolith state snapshot

### Originally tracked pressure files

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
| Annotate | P0 | `blocked` | `docs/reports/2026-04-26-annotate-parity-evidence.md` | Historical evidence captured an old oracle-side crash before upstream oracle fix `#234`; a fresh rerun is still needed. |
| Compare | P0 | `blocked` | `docs/reports/2026-04-26-compare-parity-evidence.md` | Historical evidence still shows decision-row `Accept / Split / Merge` divergence on rebuild current-main. |
| Tags / enrichments management | P0 | `pass-via-evidence-doc` | `docs/reports/2026-04-26-tags-parity-evidence.md` | Browser Tags parity passed `7/7` flows; harness also covers the underlying contracts. |
| ~~AI/chat shell~~ | P1 | `dropped` | scope decision | Dropped from rebuild parity scope on 2026-04-26. |
| Import / onboarding | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers concept/tag import, onboard start/poll, persistence, and error envelopes. |
| Compute and report modals | P1 | `blocked` | partial harness coverage | Harness covers the underlying compute/report contracts, but the modal/browser affordances themselves have not been rerun as a final browser parity pass. |
| Contact lexeme / CLEF compare extensions | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers CLEF config/catalog/providers/report plus contact-lexeme coverage and fetch lifecycles. |
| Job diagnostics | P1 | `pass-via-harness` | `parity/harness/` | Current harness covers `/api/jobs`, `/api/jobs/active`, and `/api/jobs/{jobId}/logs`. |

## Real-blocker diffs

1. **`$.server_boot_smoke.rebuild`** — current rebuild `origin/main` fails the direct script boot smoke with `NameError: _api_get_annotation is not defined`.
   - **Introduced by:** PR **#127** (`refactor(server): decompose route-domain modules`)
   - **Expected fix:** PR **#137** (`fix(server): honor env HTTP port in script mode`) which also restores script-mode startup wiring
   - **Current classification:** **real blocker** until `#137` lands on `origin/main`

## Option 1 readiness

**Not ready to replace oracle yet.** The parity meta-gate is otherwise in place (`raw=1`, `allowlisted=0`, `unallowed=1`), but the single remaining blocker is operationally critical because the rebuild cannot yet boot `python/server.py` as a script on current `origin/main`.

## Dogfood follow-up

- **Dogfood pass (Fail01):** 13 flows tested, 1 issues filed, 0 blockers. Report: `docs/reports/2026-04-27-rebuild-dogfood-report.md`. Issue links: #143.

## Coordinator sign-off

- **Lucas:** ______________________________
- **Date:** ______________________________
- **Decision:** `ready` / `near-done` / `blocked`
