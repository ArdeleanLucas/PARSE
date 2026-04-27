# PARSE-rebuild progress scorecard — 2026-04-26

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


**Date:** 2026-04-26
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`
**Rebuild SHA:** `4ffb31dd6fe6b779673ef900b2cc7f1e9fb894be`
**Oracle repo:** `ArdeleanLucas/PARSE`
**Oracle SHA:** `0951287a812609068933ba22711a8ecd97765f38`

---

## TL;DR

- **Browser/workstation runtime health:** `6/10`
- **Monolith reduction:** `5/10`
- **Parity-evidence coverage:** `1/10`
- **Desktop-distribution readiness:** `planning-stage`

Why it is not higher:
- rebuild frontend gates are green, but rebuild backend is still red on **8** pytest failures
- current oracle backend is also red on **10** pytest failures, so the parity baseline itself is imperfect
- only **2 of 5** pressure-monolith targets have materially shrunk, but `ParseUI.tsx` has now dropped from `5328` oracle LoC to `3537` on rebuild current-main
- P0 parity evidence was effectively **0/4 committed surfaces** on main at measurement time; the first Annotate evidence pass exists in open PR `#66`, not yet on `main`
- desktop packaging remains documented as **Pre-implementation planning / Not started** in `docs/distribution_readiness_checklist.md`

---

## 1. Monolith reduction table

**Axis score:** `5/10`

Scoring basis for the post-`#61/#62/#63/#58/#59` current-main snapshot:
- 5 pressure-monoliths were audited
- 2 were materially reduced on rebuild current-main
- 3 remained byte-identical to the oracle
- net reduction across the audited pressure set is now **3,006 LoC removed from 24,665 LoC** (**12.2%**)
- the main structural movement came from `ParseUI.tsx`, which fell another **887 LoC** after the AI-chat and ManageTags extractions merged

| File | Oracle LoC | Rebuild LoC | Delta | Delta % | Status | Notes |
|---|---:|---:|---:|---:|---|---|
| `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) | 8,972 | 7,757 | -1,215 | -13.5% | in-progress | HTTP extraction landed across multiple runtime slices, but the file is still the dominant backend monolith |
| `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) | 6,408 | 6,408 | 0 | 0.0% | untouched | Next active backend implementation PR is `#68` (`refactor(chat_tools): extract read-only chat tool bundles`) |
| `src/ParseUI.tsx` | 5,328 | 3,537 | -1,791 | -33.6% | in-progress | `#61` (AIChat) and `#63` (ManageTagsView) landed, materially shrinking the shell while leaving AnnotateView extraction (`#69`) still open |
| `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) | 2,050 | 2,050 | 0 | 0.0% | untouched | MCP surface is stable, but structural extraction has not started |
| `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`) | 1,907 | 1,907 | 0 | 0.0% | untouched | Provider/runtime contract remains concentrated in one file |

**Interpretation:** the rebuild has produced real structural movement, but it is concentrated in `server.py` and `ParseUI.tsx`. The rest of the pressure set is still carrying oracle-sized complexity.

---

## 2. Parity-evidence coverage table

**Axis score:** `1/10`

`docs/plans/option1-parity-inventory.md` §5.1 defines four P0 shell/workbench surfaces. At measurement time, none had a committed evidence artifact on `origin/main`; the first coordinator parity pass was still being produced separately.

| P0 surface | Evidence committed on main? | Evidence path | Current state |
|---|---|---|---|
| Shell / navigation | No | none yet | routed shell exists, but no committed oracle-vs-rebuild evidence set |
| Annotate | No | none on main at measurement time | first Saha01 Annotate pass produced separately in companion PR `#66` |
| Compare | No | none yet | compare surface is usable, but no committed parity artifact set |
| Tags / enrichments management | No | none yet | behavior exists; evidence contract still unfulfilled |

**Interpretation:** parity claims were still being made mostly from code review and spot testing rather than from committed artifacts. The evidence contract exists; coverage does not. The important upgrade is that PR `#64` now makes the baseline **red-but-classified** instead of red-and-ambiguous: the current oracle/rebuild backend failures now have named buckets, including the shared `source_index.json` Windows path-separator bug that belongs to the oracle as well as the rebuild.

---

## 3. Desktop-distribution readiness table

**Axis score:** `planning-stage`

Governing source: `docs/distribution_readiness_checklist.md`

Current checklist snapshot on 2026-04-26:
- **Current target milestone:** `Pre-implementation planning`
- **Overall readiness:** `Not started`
- **Blocker count:** `TBD`

| Desktop track | Current state | Evidence |
|---|---|---|
| Electron shell bootstrap | not started | Gate A bootstrap/runtime items all unchecked |
| Managed Python runtime | not started | Gate B runtime/dependency items all unchecked |
| Packaging artifacts (Windows/macOS) | not started | Gate B packaging artifacts unchecked |
| Update infrastructure | not started | Gate B update infrastructure unchecked |
| Signing / notarization / trust | not started | Gate C release-engineering items unchecked |
| Migration / rollback framework | not started | Gate C migration/rollback items unchecked |
| Desktop security hardening | not started | loopback-only / CORS / preload-bridge items unchecked |

**Interpretation:** the React/Vite rebuild is not the same thing as desktop shipping readiness. Desktop remains a planned architecture, not an implemented product surface.

---

## 4. Velocity (last 24h)

Grounded from merged PRs in the 24h window ending during this scorecard run.

- **Merged PRs:** `39`
- **Open PRs at measurement time:** `12` (`#64-#75`)

| PR type prefix | Count |
|---|---:|
| `refactor:` | 16 |
| `feat:` | 2 |
| `fix:` | 6 |
| `docs:` | 12 |
| `test:` | 3 |
| `chore:` | 0 |
| `other:` | 0 |

### Open PR snapshot by lane

#### Implementation lane
- `#68` — clean, all checks green; next backend chat-tools decomposition slice
- `#69` — dirty against current `main`; all historical checks green, but needs rebase before merge
- `#71` — clean, all checks green; pure ParseUI utility lift ready once merge order reaches it
- `#73` — dirty and still unrerun after upstream ParseUI churn; should follow `#69/#71`

#### Handoffs / queued work
- `#70` — clean, all checks green; Builder follow-up handoff for post-`AnnotateView` shell reduction
- `#72` — clean, all checks green; backend while-waiting research handoff
- `#74` — clean, all checks green; repo-target rule hardening for future coordinator/agent runs
- `#75` — clean, all checks green; current parse-gpt burst coordinating the remaining wave

#### Coordinator docs / parity set
- `#64` — clean, all checks green; baseline signoff with the red-but-classified backend caveat ledger
- `#65` — clean, all checks green; this scorecard, refreshed against the current 12-PR topology
- `#66` — clean, all checks green; first Annotate parity evidence set
- `#67` — clean, all checks green; `.hermes/handoffs/` queue migration

### Queue-prompt noise callout

- merged docs/handoff/coordinator prompt PRs in the same 24h window: **10** (`#59`, `#58`, `#45`, `#25`, `#22`, `#18`, `#17`, `#15`, `#10`, `#9`)
- share of all merged PRs in window: **25.6%**
- share of merged `docs:` PRs in window: **83.3%**

**Interpretation:** throughput is high, but the merge count still overstates product movement because coordination prompts remain a large share of merged docs traffic. The open-PR snapshot also shows that most remaining work is now explicit and classifiable rather than hidden in stale queue prose.

---

## 5. Coordination flags

| Flag | 2026-04-26 state | Evidence |
|---|---|---|
| Phase 0 baseline signed | pending merge in companion coordinator PR | PR `#64` now explicitly signs the baseline gate and classifies the red backend baseline |
| `.hermes` queue state freshness | in active migration | old main-branch queue PRs `#58/#59` are now merged, while PR `#67` moves future queueing into `.hermes/handoffs/` |
| parse-builder lane | implementation wave active | `#61`, `#62`, and `#63` merged; follow-on implementation `#69` and queued handoff `#70` are open |
| parse-back-end lane | implementation wave active | legacy queue PR `#59` merged; follow-on implementation `#68` and while-waiting handoff `#72` are open |
| parse-gpt lane | closing coordinator execution set | `#64-#67` remain the active coordinator docs quartet |
| Real-data parity loop | incomplete | first Annotate evidence run is open in PR `#66`; Compare and Tags evidence still pending |

**Interpretation:** the repo is active, but coordination hygiene lagged behind implementation speed. That mismatch is now material enough to deserve its own cleanup lane.

---

## 6. Recommended next 3 priorities

These are coordinator sequencing priorities, not implementation requests.

1. **Land the baseline freeze first.**  
   The rebuild needs one signed oracle SHA + fixture set + precedence order before further parity claims mean anything.

2. **Land the first committed parity evidence set and classify the oracle Annotate crash.**  
   The first Annotate Saha01 pass already shows that parity work is now blocked as much by oracle instability as by rebuild drift.

3. **Move queueing into `.hermes/handoffs/` and retire queue-prompt PR churn.**  
   The docs queue pattern is distorting merge counts and making active-lane state harder to read than it needs to be.

---

## Evidence appendix

### Oracle gate snapshot
- Frontend: `283/283` Vitest passed, TypeScript clean, build passed
- Backend: `482 passed / 10 failed / 2 skipped / 1 warning`
- Basetemp caveat: Windows conda pytest under WSL required explicit `--basetemp C:/Users/Lucas/...`

### Rebuild gate snapshot
- Frontend: `333/333` Vitest passed, TypeScript clean, build passed
- Backend: `658 passed / 8 failed / 2 skipped / 1 warning`

### Browser smoke summary
- rebuild Compare shell loaded against the seeded workspace
- rebuild Annotate loaded on Saha01 after explicit speaker selection
- current oracle Annotate entry on the same fixture can crash with a `TranscriptionLanes` hook-order error, which means parity work now needs to distinguish **rebuild drift** from **oracle instability**
