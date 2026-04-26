# PARSE-rebuild progress scorecard — 2026-04-26

**Date:** 2026-04-26  
**Rebuild repo:** `TarahAssistant/PARSE-rebuild`  
**Rebuild SHA:** `f9aa3db1aad1d77078c9105cd8b5e5254c066338`  
**Oracle repo:** `ArdeleanLucas/PARSE`  
**Oracle SHA:** `0951287a812609068933ba22711a8ecd97765f38`

---

## TL;DR

- **Browser/workstation runtime health:** `6/10`
- **Monolith reduction:** `4/10`
- **Parity-evidence coverage:** `1/10`
- **Desktop-distribution readiness:** `planning-stage`

Why it is not higher:
- rebuild frontend gates are green, but rebuild backend is still red on **8** pytest failures
- current oracle backend is also red on **10** pytest failures, so the parity baseline itself is imperfect
- only **2 of 5** pressure-monolith targets have materially shrunk; `chat_tools.py`, `mcp_adapter.py`, and `provider.py` are still untouched
- P0 parity evidence was effectively **0/4 committed surfaces** on main at measurement time
- desktop packaging remains documented as **Pre-implementation planning / Not started** in `docs/distribution_readiness_checklist.md`

---

## 1. Monolith reduction table

**Axis score:** `4/10`

Scoring basis for 2026-04-26:
- 5 pressure-monoliths were audited
- 2 were materially reduced on rebuild current-main
- 3 remained byte-identical to the oracle
- net reduction across the audited pressure set was **2,139 LoC removed from 24,665 LoC** (**8.7%**)

| File | Oracle LoC | Rebuild LoC | Delta | Delta % | Status | Notes |
|---|---:|---:|---:|---:|---|---|
| `python/server.py` | 8,972 | 7,757 | -1,215 | -13.5% | in-progress | HTTP extraction landed across multiple runtime slices, but the file is still the dominant backend monolith |
| `python/ai/chat_tools.py` | 6,408 | 6,408 | 0 | 0.0% | untouched | Next queued backend lane is explicit chat-tools decomposition (open queue PR `#59`) |
| `src/ParseUI.tsx` | 5,328 | 4,404 | -924 | -17.3% | structurally-cracked | Unified shell has shrunk, but annotate/AI/shell logic still sits in one oversized React file |
| `python/adapters/mcp_adapter.py` | 2,050 | 2,050 | 0 | 0.0% | untouched | MCP surface is stable, but structural extraction has not started |
| `python/ai/provider.py` | 1,907 | 1,907 | 0 | 0.0% | untouched | Provider/runtime contract remains concentrated in one file |

**Interpretation:** the rebuild has produced real structural movement, but it is concentrated in `server.py` and `ParseUI.tsx`. The rest of the pressure set is still carrying oracle-sized complexity.

---

## 2. Parity-evidence coverage table

**Axis score:** `1/10`

`docs/plans/option1-parity-inventory.md` §5.1 defines four P0 shell/workbench surfaces. At measurement time, none had a committed evidence artifact on `origin/main`; the first coordinator parity pass was still being produced separately.

| P0 surface | Evidence committed on main? | Evidence path | Current state |
|---|---|---|---|
| Shell / navigation | No | none yet | routed shell exists, but no committed oracle-vs-rebuild evidence set |
| Annotate | No | none on main at measurement time | first Saha01 Annotate pass produced separately in a companion coordinator PR |
| Compare | No | none yet | compare surface is usable, but no committed parity artifact set |
| Tags / enrichments management | No | none yet | behavior exists; evidence contract still unfulfilled |

**Interpretation:** parity claims were still being made mostly from code review and spot testing rather than from committed artifacts. The evidence contract exists; coverage does not.

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

- **Merged PRs:** `34`
- **Open PRs at measurement time:** `#61`, `#60`, `#59`, `#58`

| PR type prefix | Count |
|---|---:|
| `refactor:` | 14 |
| `feat:` | 2 |
| `fix:` | 6 |
| `docs:` | 10 |
| `test:` | 2 |
| `chore:` | 0 |
| `other:` | 0 |

### Queue-prompt noise callout

- `docs:` PRs that were primarily queue/handoff/coordinator prompts in the same 24h window: **7**
- Share of all merged PRs in window: **20.6%**
- Share of merged `docs:` PRs in window: **70.0%**

**Interpretation:** throughput is high, but the merge count overstates product movement because coordinator queue prompts are still flowing through main-branch PRs.

---

## 5. Coordination flags

| Flag | 2026-04-26 state | Evidence |
|---|---|---|
| Phase 0 baseline signed | pending merge in companion coordinator PR | baseline data collected; see companion baseline-signoff PR work |
| `.hermes` queue state freshness | stale on main | legacy `.hermes/automation/*` state reflected pre-merge-wave data and much of it was gitignored/local-only |
| parse-builder lane | queued + one live implementation PR | open queue PR `#58`; live implementation PR `#61` |
| parse-back-end lane | queued | open queue PR `#59` |
| parse-gpt lane | still using old queue-PR pattern | open queue PR `#60`; cleanup not yet landed |
| Real-data parity loop | incomplete | first Annotate evidence run still being produced separately |

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
