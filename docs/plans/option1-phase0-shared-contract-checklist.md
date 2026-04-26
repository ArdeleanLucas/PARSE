# PARSE Option-1 Rebuild — Phase 0 Shared Contract Checklist

**Status:** Coordinator baseline signed (Sections 2-3 completed; broader Phase 0 checklist remains open)
**Date:** 2026-04-26
**Depends on:**
- `docs/plans/option1-separate-rebuild-to-option3-desktop-platform.md`
- `docs/plans/option1-two-agent-parallel-rebuild-plan.md`
- `docs/plans/option1-parity-inventory.md`
- `docs/desktop_product_architecture.md`
- current oracle files under `src/`, `python/`, and project artifacts

**Primary goal:** freeze the shared contract that both main rebuild agents must obey before any parallel implementation work begins.

**Coordinator note (2026-04-26):** parallel implementation already started before this baseline sign-off. This update does **not** pretend the earlier merge wave never happened; it retroactively records the real oracle baseline, fixture set, precedence order, and gate evidence the active lanes are already expected to follow.

---

## 1. Blocking rule

Phase 0 is a **hard blocker**.

Agent A and Agent B do **not** begin divergent implementation until this checklist is complete and explicitly signed off.

### Phase 0 non-goals

- no broad feature implementation
- no speculative architecture churn beyond the approved rebuild skeleton
- no agent-specific contract forks
- no redefining parity targets mid-flight

---

## 2. Canonical inputs and precedence order

The coordinator must freeze a precedence order so agents do not argue from different sources.

### 2.1 Required source set

- [x] `docs/plans/option1-separate-rebuild-to-option3-desktop-platform.md`
- [x] `docs/plans/option1-two-agent-parallel-rebuild-plan.md`
- [x] `docs/plans/option1-parity-inventory.md`
- [x] `docs/desktop_product_architecture.md`
- [x] `AGENTS.md`
- [x] `src/api/client.ts`
- [x] `package.json`
- [x] selected backend route/tests in `python/` (`python/server.py`, `python/test_external_api_surface.py`, `python/test_server_static_paths.py`, `python/ai/test_parse_memory_tool.py`)
- [x] selected oracle project fixtures / exports / sample outputs (2026-04-26 Saha01 parity fixture seeded from `/home/lucas/parse-workspace`, plus current LingPy/export-facing workspace metadata)

### 2.2 Precedence order to record

- [x] product/architecture docs outrank implementation guesses
- [x] current oracle code outranks stale planning assumptions
- [x] coordinator decisions outrank lane-local convenience changes
- [x] any unresolved contradiction is escalated before implementation starts

Recorded 2026-04-26 precedence order:
1. Target-shape questions default to `docs/plans/option1-separate-rebuild-to-option3-desktop-platform.md`, `docs/plans/option1-two-agent-parallel-rebuild-plan.md`, and `docs/desktop_product_architecture.md`.
2. Runtime/API behavior defaults to current oracle code at `ArdeleanLucas/PARSE@0951287a812609068933ba22711a8ecd97765f38`.
3. When docs and code disagree, coordinator-written rebuild contract docs resolve the ambiguity explicitly instead of allowing lane-local forks.
4. If neither the docs nor the oracle code settle the question cleanly, the contradiction is logged and escalated rather than papered over in a lane PR.

---

## 3. Oracle baseline record

The coordinator records the exact current PARSE baseline used for rebuild parity.

| Field | Record before parallel start |
|---|---|
| Oracle repo path | `/home/lucas/gh/ardeleanlucas/parse` |
| Oracle branch | `origin/main` |
| Oracle commit SHA | `0951287a812609068933ba22711a8ecd97765f38` |
| Freeze date/time | `2026-04-26T15:55:55Z` (UTC) |
| Frontend validation evidence | `.hermes/reports/2026-04-26-oracle-frontend-gate.txt` — Vitest `283/283` passed, `./node_modules/.bin/tsc --noEmit` clean, `npm run build` passed |
| Backend/API validation evidence | `.hermes/reports/2026-04-26-oracle-backend-gate.txt` — Windows conda pytest with explicit `--basetemp` produced `482 passed / 10 failed / 2 skipped / 1 warning`; rebuild comparison companion stored in `.hermes/reports/2026-04-26-rebuild-backend-gate.txt` (`658 passed / 8 failed / 2 skipped / 1 warning`) |
| Fixture dataset version | `Saha01` single-speaker parity fixture derived 2026-04-26 from `/home/lucas/parse-workspace` (`project.json` + `source_index.json` restricted to `Saha01`, `concepts.csv`, `annotations/Saha01.parse.json`, `annotations/Saha01.json`, `peaks/Saha01.json`, `coarse_transcripts/Saha01.json`, `audio/original/working/Saha01/Sahana_F_1978.wav`) |
| Known accepted oracle quirks | 1. Windows conda pytest under WSL requires explicit `--basetemp C:/Users/Lucas/...`. <br>2. Browser parity should use the React SPA through Vite (`5173`), not raw backend root `8766/`, which serves a directory listing. <br>3. The current oracle backend suite is red on 10 known failures; the baseline is recorded as-is rather than selecting a friendlier SHA. <br>4. On the Saha01 parity fixture, current oracle Annotate entry can crash with `Rendered more hooks than during the previous render` in `TranscriptionLanes.tsx`; this is baseline behavior for 2026-04-26 evidence, not a rebuild-only invention. |

### Required completion items

- [x] baseline SHA recorded
- [x] fixture set recorded
- [x] any known contract quirks called out explicitly
- [x] both main agents acknowledge the same baseline

Acknowledgement basis on 2026-04-26: the active lane handoff PRs already reference the same rebuild/oracle SHA pair — parse-builder `#58` and parse-back-end `#59` both queue work against rebuild `f9aa3db1aa` and oracle `0951287a81`.

---

## 4. Freeze the rebuild-repo skeleton

The top-level rebuild shape must be fixed before work splits.

### 4.1 Required top-level shape

```text
<rebuild-repo>/
  README.md
  desktop/
  frontend/
  backend/
  parity/
  docs/
```

### 4.2 Skeleton checklist

- [ ] top-level directories frozen
- [ ] coordinator-owned directories frozen
- [ ] Agent A owned directories frozen
- [ ] Agent B owned directories frozen
- [ ] naming conventions for new modules/components/hooks/services documented
- [ ] shared root config files listed explicitly
- [ ] no ambiguous shared subtree remains

### 4.3 Ownership reminder

Use the ownership model already defined in the two-agent execution plan:

- **Coordinator-only:** root docs/contracts/CI/shared config after Phase 0, plus `parity/contracts/**`, `parity/fixtures/**`, and `parity/deviations.md`
- **Agent A:** `desktop/**`, `frontend/**`, `parity/ui/**`
- **Agent B:** `backend/**`, `parity/api/**`, `parity/jobs/**`, `parity/export/**`

Any exception must be recorded before coding starts.

---

## 5. Freeze bootstrap and tooling contract

Both lanes must start from the same executable bootstrap rules.

### 5.1 Runtime/tooling decisions to record

- [ ] Node version / package manager decision
- [ ] Python version decision
- [ ] lockfile strategy
- [ ] repo bootstrap commands
- [ ] CI baseline jobs
- [ ] local dev startup commands

### 5.2 Minimum bootstrap gates

| Command | Why it matters | Phase 0 pass condition |
|---|---|---|
| `npm install` | frontend bootstrap reproducibility | installs cleanly from a fresh checkout |
| `npm run test -- --run` | frontend regression gate | green in baseline rebuild scaffold |
| `./node_modules/.bin/tsc --noEmit` | TypeScript strictness gate | green in baseline rebuild scaffold |
| `python3 -m pytest -q` | backend bootstrap/test gate | green in baseline rebuild scaffold |

These commands assume the coordinator freezes a **root workspace** topology in Phase 0. If the rebuild uses split manifests instead, the exact equivalent frontend/backend commands must be recorded here before sign-off.

### 5.3 Decisions to make explicitly

- [ ] whether `npm run test:api` is a Phase-0 baseline gate or a Phase-1 follow-up gate
- [ ] where shared type generation or schema snapshots live, if any
- [ ] whether the rebuild uses one workspace root or split package manifests from day one

If any of these are left vague, Phase 0 is not done.

---

## 6. Freeze desktop ↔ backend handshake

The desktop runtime boundary must be explicit before Agent A and Agent B diverge.

### 6.1 Baseline contract to record

From the desktop architecture plan, the shell/backend handshake must define:

- [ ] backend host policy (`127.0.0.1`)
- [ ] port policy (`--port 0` / ephemeral port)
- [ ] project-root handoff
- [ ] auth-token handoff
- [ ] user-data-root handoff
- [ ] readiness/health handshake
- [ ] renderer load timing after backend readiness
- [ ] failure UI / restart / fail-fast policy

### 6.2 Coordinator questions that must be answered

- [ ] which readiness endpoint or payload counts as backend-ready
- [ ] what timeout/retry policy the shell uses before showing an error
- [ ] which failures are recoverable warnings vs hard launch blockers
- [ ] where desktop logs live during rebuild development

No lane should invent its own startup semantics.

---

## 7. Freeze workbench and route inventory

The coordinator must freeze what the rebuild shell contains before parallel implementation begins.

### 7.1 In-scope current workbenches / surfaces

- [ ] shell / navigation
- [ ] Annotate
- [ ] Compare
- [ ] Tags / management surfaces
- [ ] AI/chat shell surfaces currently exposed to users
- [ ] import / onboarding / comments / tags / concepts flows
- [ ] compute/report/config surfaces required by current workflows

### 7.2 Phase-3 reserved placeholders

These may be reserved in the shell plan but are **not** initial parity targets unless explicitly approved:

- [ ] `training`
- [ ] `phonetics`
- [ ] `linguistics`

### 7.3 Route inventory questions to settle

- [ ] whether the rebuild uses multiple explicit routes or a shell with internal workbench switching
- [ ] reserved route/path names
- [ ] entrypoint for project-open / create-project flow
- [ ] location of auth/config/settings surfaces

The route inventory must be frozen before Agent A builds navigation and before Agent B relies on frontend entry assumptions.

---

## 8. Freeze HTTP API contract inventory

The current frontend helper surface in `src/api/client.ts` is the baseline API inventory.

### 8.1 Contract groups that must be frozen

- [ ] annotations + STT segments
- [ ] enrichments + config + pipeline state
- [ ] tags + lexeme notes + CSV imports
- [ ] auth
- [ ] STT / normalize / onboard
- [ ] offset detection / apply
- [ ] suggestions + lexeme search
- [ ] chat + generic compute
- [ ] active jobs + job logs
- [ ] export + spectrogram
- [ ] contact lexeme + CLEF config/catalog/reporting

### 8.2 Contract details to record per group

- [ ] method/path
- [ ] request shape
- [ ] response shape
- [ ] error semantics
- [ ] job start/poll semantics, when applicable
- [ ] compatibility aliases already expected by current UI

### 8.3 Known compatibility quirks to preserve or deliberately retire

Record them explicitly before implementation starts, for example:

- [ ] field aliases such as `job_id` / `jobId` where the current UI expects compatibility
- [ ] session identifier compatibility such as `session_id` / `sessionId`, where applicable
- [ ] accepted terminal status values already consumed by the current UI
- [ ] provider-specific auth or parameter behavior that must remain compatible during rebuild

---

## 9. Freeze parity artifact layout and fixture set

Parity evidence must have a stable home before teams start producing it.

### 9.1 Required `parity/` layout

```text
parity/
  contracts/
  ui/
  api/
  jobs/
  export/
  fixtures/
  deviations.md
```

### 9.2 Artifact rules

- [ ] naming convention recorded
- [ ] metadata fields recorded: date, oracle SHA, rebuild SHA, owner, scenario
- [ ] location for screenshots recorded
- [ ] location for API snapshots recorded
- [ ] location for export goldens recorded
- [ ] location for deviation log recorded

### 9.3 Fixture checklist

- [ ] selected speaker fixture set
- [ ] selected compare/enrichment fixture set
- [ ] selected export fixture set
- [ ] one failure-path fixture where relevant
- [ ] deterministic reset/reload instructions
- [ ] no hidden scaffold/fallback data policy recorded

---

## 10. Freeze test gates and review cadence

### 10.1 Per-track expectations

- [ ] Agent A local gates defined
- [ ] Agent B local gates defined
- [ ] coordinator reintegration gates defined
- [ ] parity review cadence defined at the end of each major phase

### 10.2 Minimum cadence rules

- [ ] every major phase ends with parity evidence, not just code completion
- [ ] deviations are logged instead of silently normalized away
- [ ] integration review happens on the coordinator lane, not by direct A ↔ B merges
- [ ] failures block forward claims until classified as bug, accepted gap, or deliberate redesign

---

## 11. Freeze branch, worktree, and merge strategy

### 11.1 Branches to create and record

- [ ] `feat/rebuild-track-a-frontend-desktop`
- [ ] `feat/rebuild-track-b-backend-parity`
- [ ] `feat/rebuild-integration`

### 11.2 Worktrees to create and record

- [ ] `frontend-desktop/`
- [ ] `backend-parity/`
- [ ] `integration/`

### 11.3 Merge policy to freeze

- [ ] Agent A never merges directly into Agent B
- [ ] Agent B never merges directly into Agent A
- [ ] both lanes merge only through the integration lane
- [ ] only the coordinator resolves cross-track conflicts
- [ ] one write subagent per owned subtree at a time

---

## 12. Ready-to-parallelize definition

Parallel rebuild work may start only when every item below is true.

- [ ] oracle SHA is frozen
- [ ] parity inventory is approved
- [ ] rebuild skeleton is frozen
- [ ] bootstrap/tooling gates are frozen
- [ ] desktop/backend handshake is frozen
- [ ] route/workbench inventory is frozen
- [ ] API contract inventory is frozen
- [ ] parity artifact layout and fixtures are frozen
- [ ] branch/worktree strategy is frozen
- [ ] ownership boundaries are acknowledged by both main agents
- [ ] coordinator signs off that Phase 0 is complete

### Sign-off record

| Role | Name | Date | Notes |
|---|---|---|---|
| Coordinator | parse-gpt | 2026-04-26 | Baseline freeze recorded; broader Phase 0 checklist remains open. |
| Agent A owner | parse-builder lane | 2026-04-26 | Queue-time baseline in PR #58 already matches coordinator freeze (`f9aa3db1aa` / `0951287a81`). |
| Agent B owner | parse-back-end lane | 2026-04-26 | Queue-time baseline in PR #59 already matches coordinator freeze (`f9aa3db1aa` / `0951287a81`). |

---

## 13. Change control after Phase 0

Once Phase 0 is signed off:

- contract changes require coordinator approval
- shared contract docs are updated before implementation claims continue
- both main agents must acknowledge reopened shared contracts
- accidental drift is treated as a defect, not as a local convenience edit

### Reopen checklist

If a shared contract must change mid-rebuild, record:

- [ ] reason for reopening
- [ ] affected files/surfaces
- [ ] owner
- [ ] rollback or migration path
- [ ] new parity evidence required

---

## 14. Immediate next actions after this checklist lands

1. Fill the oracle baseline record.
2. Convert the parity inventory into concrete rows/artifacts in the rebuild repo.
3. Bootstrap the separate rebuild repo using the frozen skeleton and gate commands.
4. Start Agent A and Agent B only after the coordinator signs the Ready-to-Parallelize section.
