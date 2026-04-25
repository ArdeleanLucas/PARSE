# PARSE Option-1 Rebuild: Two-Agent Parallel Execution Plan

**Status:** Proposed execution-planning doc for the separate rebuild repo  
**Date:** 2026-04-25  
**Depends on:**
- `docs/plans/option1-separate-rebuild-to-option3-desktop-platform.md`
- `docs/plans/option1-parity-inventory.md`
- `docs/plans/option1-phase0-shared-contract-checklist.md`

**Primary goal:** execute the separate rebuild repo efficiently with **two main agents in parallel**, each allowed to use **subagents within owned boundaries**, without colliding on the same files.

---

## 1. Executive summary

This plan assumes PARSE will be rebuilt in a **separate repo** using **Option 1 / domain-preserving modularization** first, while keeping the current PARSE repo as the behavior oracle.

Execution will use:
- **one coordinator** (human + planning agent role)
- **two main implementation agents** running in parallel
- **multiple subagents** inside each main agent's lane, but only within file-ownership boundaries

The key principle is:

> **Parallelize by stable file ownership, not by abstract responsibility.**

That means we do **not** split by “UI vs logic” or “frontend vs state” in overlapping files. We split by **owned subtrees** plus a **shared contract gate** before implementation starts.

---

## 2. Roles

## 2.1 Coordinator

The coordinator owns:
- the current PARSE repo planning/docs PRs
- rebuild-repo bootstrap decisions
- shared contracts
- merge/integration leadership
- parity acceptance criteria
- conflict arbitration

The coordinator does **not** implement broad feature slices directly once the two main lanes start.

## 2.2 Agent A — Frontend + desktop shell lane

Agent A owns:
- desktop shell scaffolding inside the rebuild repo
- frontend shell/navigation/layout
- page/workbench UI composition
- frontend state wiring
- UI parity artifacts

## 2.3 Agent B — Backend + parity/contracts lane

Agent B owns:
- backend app/bootstrap/routes/services
- AI/compare decomposition in the rebuild repo
- API/job/export parity artifacts
- contract conformance checks
- backend observability surfaces needed by the rebuilt app

---

## 3. Rebuild-repo ownership table (hard boundary)

## 3.1 Coordinator-only files/directories

These must be written once and then treated as frozen/shared unless the coordinator explicitly reopens them:

```text
<rebuild-repo>/
  README.md
  docs/
  docs/contracts/
  docs/architecture/
  parity/contracts/
  parity/fixtures/
  parity/deviations.md
  .github/workflows/
  root toolchain/bootstrap config
```

Examples:
- root README
- architecture docs
- parity contract snapshots / schemas
- shared fixtures and deviation log
- CI workflow files
- top-level workspace metadata

## 3.2 Agent A owned subtree

```text
<rebuild-repo>/
  desktop/
  frontend/
  parity/ui/
```

Agent A may also create read-only notes under:
- `docs/track-a/`

but does not edit coordinator-owned docs after Phase 0 without approval.

## 3.3 Agent B owned subtree

```text
<rebuild-repo>/
  backend/
  parity/api/
  parity/jobs/
  parity/export/
```

Agent B may also create read-only notes under:
- `docs/track-b/`

but does not edit coordinator-owned docs after Phase 0 without approval.

## 3.4 Explicit no-touch rule

- Agent A never writes `backend/**`
- Agent B never writes `frontend/**` or `desktop/**`
- Neither agent rewrites root bootstrap/config after Phase 0
- Shared contract files are coordinator-owned and treated as **immutable unless reopened**

---

## 4. Shared contract gate (Phase 0 — blocker)

No implementation starts until Phase 0 is complete.

## 4.1 Shared contract deliverables

The coordinator must define and freeze:

1. **Behavior oracle set**
   - which current PARSE pages/workflows are in rebuild parity scope
   - recorded in `docs/plans/option1-parity-inventory.md`, including which rows are P0 vs P1
   - initial scope includes annotate / compare / tags / export / jobs / auth / desktop bootstrap

2. **Rebuild-repo skeleton**
   - repo layout
   - root toolchain
   - CI scaffold
   - dev bootstrap commands

3. **Desktop bootstrap contract**
   - how desktop shell launches backend
   - port/auth token behavior
   - readiness/health handshake

4. **API contract inventory**
   - page-critical endpoints
   - request/response shapes
   - job state payloads
   - error semantics

5. **Parity artifact layout**
   - what lives under `parity/ui`, `parity/api`, `parity/jobs`, `parity/export`, `parity/contracts`, `parity/fixtures`, and `parity/deviations.md`

6. **Page/workbench inventory**
   - current: Annotate, Compare, Tags, chat/compute shell
   - future placeholders allowed later: training, phonetics, computational-linguistics tools

7. **Coordinator gate checklist**
   - completion tracked in `docs/plans/option1-phase0-shared-contract-checklist.md`

## 4.2 Gate commands

Before tracks diverge, both agents must be able to run the same baseline commands successfully in the rebuild repo.

These commands assume the coordinator froze a **root workspace** shape in Phase 0. If the rebuild instead uses split manifests, the coordinator must record the exact equivalent frontend/backend commands in `docs/plans/option1-phase0-shared-contract-checklist.md` before parallel work starts:

```bash
# frontend shell available
npm install
npm run test -- --run
./node_modules/.bin/tsc --noEmit

# backend test bootstrap available
python3 -m pytest -q
```

If Phase 0 is not green, parallel work does not start.

---

## 5. Branch and worktree strategy

## 5.1 Branches

Inside the rebuild repo, use three long-lived branches:

- `feat/rebuild-track-a-frontend-desktop`
- `feat/rebuild-track-b-backend-parity`
- `feat/rebuild-integration`

## 5.2 Worktrees

Use three worktrees:

```text
<rebuild-worktrees>/
  frontend-desktop/
  backend-parity/
  integration/
```

## 5.3 Merge rule

- Agent A and Agent B never merge directly into each other
- both merge into `feat/rebuild-integration`
- only the coordinator resolves integration conflicts

---

## 6. How subagents are allowed to work

## 6.1 Subagent rule

Each main agent may use subagents, but only inside its owned subtree.

## 6.2 Allowed subagent patterns

### Agent A subagents
- `desktop bootstrap shell`
- `frontend shell/router/layout`
- `Annotate page slice`
- `Compare page slice`
- `shared UI primitives within frontend-owned tree`
- `UI parity test cases`

### Agent B subagents
- `route module extraction`
- `service layer extraction`
- `job registry/progress/streaming surfaces`
- `chat/AI tool decomposition`
- `compare backend decomposition`
- `API/export/job parity harness`

## 6.3 Forbidden subagent patterns

- No subagent may edit both frontend and backend in one task
- No two write subagents may target the same subtree simultaneously
- No subagent touches coordinator-owned contract files unless explicitly delegated

---

## 7. Parallel execution phases

## Phase 0 — Bootstrap + contract freeze (Coordinator)

Deliverables:
- rebuild repo created
- root skeleton exists
- contracts frozen
- parity directories created
- CI/dev baseline green

At the end of Phase 0:
- Agent A starts from a stable frontend/desktop shell
- Agent B starts from a stable backend/app shell

---

## Phase 1 — Parallel foundation lanes

### Agent A (frontend + desktop)

Owns:
- `desktop/**`
- `frontend/**`
- `parity/ui/**`

Objectives:
- desktop shell bootstrap
- frontend app shell
- navigation and page placeholders
- base stores/hooks organization
- initial UI parity checklist

Suggested subagent split:
1. **A1** — desktop shell bootstrap (`desktop/**`)
2. **A2** — frontend app shell/router/layout (`frontend/src/app/**`)
3. **A3** — UI primitives + shell page containers (`frontend/src/components/shell/**`, `frontend/src/components/shared/**`)
4. **A4** — UI parity checklist scaffold (`parity/ui/**`)

### Agent B (backend + parity)

Owns:
- `backend/**`
- `parity/api/**`
- `parity/jobs/**`
- `parity/export/**`

Objectives:
- backend bootstrap shell
- route modules
- service boundaries
- job/streaming skeleton
- API/job/export parity harness

Suggested subagent split:
1. **B1** — backend bootstrap + route registry (`backend/app/**`)
2. **B2** — route/service split for annotations/config/enrichments/export
3. **B3** — job registry / job status / streaming scaffolding
4. **B4** — parity harness for API/job/export comparison

### Phase-1 conflict prevention

- Agent A never edits route/service/backend files
- Agent B never edits UI/shell/desktop files
- Shared page names and route names are fixed by Phase 0 contract, not renegotiated in implementation threads

---

## Phase 2 — Core workflow rebuild in parallel

### Agent A track

Objectives:
- rebuilt Annotate page
- rebuilt Compare page
- rebuilt Tags/management flow
- maintained shell navigation between them

Suggested subagent split:
1. **A5** — Annotate page skeleton and interactions
2. **A6** — Compare page skeleton and interactions
3. **A7** — Tags/manage flow
4. **A8** — shell-level shared controls (mode switcher, drawers, chat dock placeholders)

### Agent B track

Objectives:
- annotation backend behavior parity
- compare backend behavior parity
- export parity
- auth/job parity for the rebuilt frontend to consume

Suggested subagent split:
1. **B5** — annotation routes/services
2. **B6** — compare routes/services
3. **B7** — export/auth/job behavior
4. **B8** — parity snapshots + fixtures for these flows

### Phase-2 conflict prevention

- Agent A consumes backend contracts; does not redefine them
- Agent B preserves response semantics; does not redesign UI assumptions without coordinator approval
- parity failures are logged in `parity/**`, not “fixed silently” by changing the oracle

---

## Phase 3 — Advanced compute / AI / agent surfaces

### Agent A track

Objectives:
- polished desktop UX
- non-specialist usability improvements in the rebuilt shell
- future-page scaffolding for later workbenches

Suggested subagent split:
1. **A9** — desktop UX polish, onboarding, project-open flow
2. **A10** — shell extensibility for future pages (`training`, `phonetics`, `linguistics` placeholders)
3. **A11** — UI parity and usability checklist expansion

### Agent B track

Objectives:
- decompose `chat_tools.py`
- rebuild AI/chat/tool surfaces
- MCP/OpenAPI/streaming parity
- harden backend for local desktop runtime

Suggested subagent split:
1. **B9** — AI/chat route + service split
2. **B10** — MCP/OpenAPI surfaces
3. **B11** — streaming/job/event parity
4. **B12** — desktop-local runtime hardening

### Why Phase 3 is still safe in parallel

Because by this point:
- Agent A owns the outer shell and usability/page expansion
- Agent B owns the internal engine and agent surfaces
- their file systems remain largely disjoint

---

## Phase 4 — Integration and promotion toward Option 3

This phase is **not parallel-owned**.

The coordinator leads integration in `feat/rebuild-integration`.

Deliverables:
- merged frontend + backend rebuild
- parity review against current PARSE
- package extraction candidates identified
- first Option-3 promotion plan prepared

Only after this phase should the rebuild begin promoting toward:
- `desktop/`
- `frontend/`
- `backend/`
- `packages/`

as a more formal platform split.

---

## 8. Testing and parity rules

## 8.1 Continuous testing rule

Every track must test as it goes.

### Agent A must keep green
- UI tests for frontend-owned code
- typecheck for frontend-owned code
- browser parity checklist updates

### Agent B must keep green
- backend unit/integration tests
- route parity snapshots
- job/export parity checks

## 8.2 Shared parity review cadence

At the end of each major phase:
1. compare rebuilt behavior against current PARSE
2. record deviations explicitly
3. decide whether deviation is:
   - bug
   - accepted temporary gap
   - deliberate redesign

No hidden drift.

---

## 9. Concrete anti-collision rules

1. **Single-writer ownership per subtree**
2. **Coordinator owns contracts/docs/CI/root config after Phase 0**
3. **No direct Agent A ↔ Agent B merges**
4. **Subagents inherit ownership limits from their parent agent**
5. **One write subagent per owned subtree at a time**
6. **Cross-track changes require coordinator approval first**
7. **No redefining parity oracle behavior inside the rebuild repo**

---

## 10. Success criteria

This execution plan succeeds if:
1. Two main agents can work for long stretches without merge collisions.
2. Subagents accelerate implementation instead of creating duplicate edits.
3. The rebuild repo reaches parity faster than an in-place rewrite would.
4. The codebase remains clean enough to promote from Option 1 to Option 3 later.

---

## 11. Immediate next actions if this plan is accepted

1. Create the separate rebuild repo.
2. Let the coordinator land the Phase 0 bootstrap + contract inventory using:
   - `docs/plans/option1-parity-inventory.md`
   - `docs/plans/option1-phase0-shared-contract-checklist.md`
3. Start Agent A and Agent B from their dedicated worktrees/branches only after the Phase-0 checklist is signed off.
4. Require parity evidence at the end of every phase, not just at the end of the rebuild.
