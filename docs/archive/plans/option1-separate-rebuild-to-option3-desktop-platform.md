> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../../).

# PARSE Separate-Rebuild Plan: Option 1 Now, Option 3 Later

> **Post-decomp note (2026-04-27):** pre-refactor file paths mentioned below may refer to barrels or orchestrator entrypoints rather than the concrete implementation files now used on `main`. Use [`docs/architecture/post-decomp-file-map.md`](/docs/architecture/post-decomp-file-map.md) as the canonical current-layout reference.


> **CANCELLED 2026-04-26** — Option 3 (desktop platform pivot) is not happening. Per Lucas decision: Option 1 (modular rebuild) only. The rebuild's done-state is monolith decomposition + parity evidence complete on the React/web stack. Desktop product work is dropped, not deferred. This document remains for historical context; do not act on the Option 3 sections.


**Status:** Proposed plan-only PR  
**Date:** 2026-04-25  
**Applies to:** current `origin/main` as the behavior oracle; implementation happens in a separate rebuild repo  
**Decision type:** architecture + delivery strategy

---

## 1. Executive summary

PARSE should **not** attempt a full in-place rewrite inside the current repo.

Instead, the immediate plan is:

1. **Document the current repo as the canonical behavior/specification source**.
2. **Rebuild the app in a separate repo**.
3. Use **Option 1 (domain-preserving modularization)** as the initial architecture in that rebuild effort.
4. **Test for behavior parity continuously as the rebuild progresses**.
5. Once the rebuilt app reaches functional parity and desktop viability, **promote the rebuilt codebase toward Option 3** — the desktop-product / platform-oriented architecture.

So the strategy is:

> **Build now with Option 1 discipline, in a separate repo, while deliberately aiming for Option 3 as the long-term destination.**

---

## 2. Why this plan exists

The current PARSE codebase has multiple monoliths large enough that a safe in-place rewrite is likely to stall feature work and blur regression ownership.

### Verified monolith pressure points

- `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`) — ~8962 lines
- `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) — ~6408 lines
- `src/ParseUI.tsx` — ~5327 lines
- `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) — ~2050 lines
- `python/ai/provider.py` (base-provider surface; concrete providers live under `python/ai/providers/`) — ~1907 lines

### Verified current domain structure worth preserving

Frontend already has meaningful domains:
- `src/components/annotate/`
- `src/components/compare/`
- `src/components/compute/`
- `src/components/shared/`
- `src/hooks/`, `src/stores/`, `src/api/`

Backend already has meaningful domains:
- `python/ai/`
- `python/compare/`
- `python/external_api/`
- `python/adapters/`
- `python/workers/`
- `python/shared/`
- `python/packages/parse_mcp/`

The repo also already signals a desktop/platform future:
- `desktop/README.md` scaffold
- `docs/desktop_product_architecture.md` as canonical desktop plan
- `python/packages/parse_mcp/` publishable wrapper package
- `python/external_api/` OpenAPI + HTTP MCP bridge + streaming

---

## 3. Core architectural decision

## 3.1 Immediate implementation strategy: **Option 1**

The rebuilt app should begin with **domain-preserving modularization**.

That means:
- preserve the strong domain concepts already present in the current PARSE repo
- split the monoliths into smaller modules inside those domains
- avoid a massive package/repo reset while parity is still being established

## 3.2 Long-term destination: **Option 3**

Once the rebuilt app is stable and parity-tested, the codebase should move toward a desktop-product / platform split:
- desktop shell
- frontend UI app
- backend engine/services
- shared packages/contracts
- agent-facing and external-client packages

This is the architecture that best supports:
- a standalone desktop app
- non-specialist usability
- multiple future pages/workbenches
- agent interoperability
- typed contracts and reusable linguistics tooling

---

## 4. Delivery decision: rebuild in a separate repo

## 4.1 Why separate repo instead of in-place rewrite

A separate rebuild repo is preferred because it:
- protects the current PARSE runtime from architectural churn
- lets current PARSE continue serving as the working reference implementation
- enables clean parity testing against the current app
- avoids half-migrated states landing on `origin/main`
- keeps thesis-critical usage unblocked while the rebuild advances

## 4.2 Role of the current PARSE repo during the rebuild

The current repo remains:
- the **behavior oracle**
- the **API contract oracle**
- the **data-format oracle**
- the **export correctness oracle**
- the **fallback runtime**

The rebuild repo is where the new implementation is assembled and tested.

## 4.3 Repo naming

Final rebuild repo name is still a decision.

Working placeholder names:
- `parse-next`
- `parse-desktop-rebuild`
- `parse-platform`

This plan intentionally does not hard-code a final repo name.

---

## 5. Recommended rebuild-repo shape for Phase 1

Even though the immediate strategy is Option 1, the rebuild repo can still be laid out to make the later Option 3 migration easier.

### Recommended Phase-1 rebuild tree

```text
<rebuild-repo>/
├── desktop/
│   ├── electron-main/
│   ├── preload/
│   └── packaging/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── annotate/
│   │   │   ├── compare/
│   │   │   ├── compute/
│   │   │   ├── shell/
│   │   │   └── shared/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── lib/
│   │   └── workers/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── jobs/
│   │   ├── http/
│   │   ├── services/
│   │   └── bootstrap.py
│   ├── ai/
│   ├── compare/
│   ├── external_api/
│   ├── adapters/
│   ├── workers/
│   ├── shared/
│   └── tests/
├── parity/
│   ├── fixtures/
│   ├── contracts/
│   ├── ui/
│   │   ├── checklists/
│   │   └── screenshots/
│   ├── api/
│   │   ├── snapshots/
│   │   └── contract-tests/
│   ├── jobs/
│   ├── export/
│   └── deviations.md
└── docs/
```

### Why this is still “Option 1” in practice

Because the structure preserves the current domains:
- annotate
- compare
- compute
- shared
- ai
- compare backend
- external API
- adapters
- workers

It does **not** yet force a full package/platform split inside the code itself.

---

## 6. What “move to Option 3” means later

After parity and desktop viability are established, the rebuild repo should evolve toward:

```text
<future-parse-platform>/
├── desktop/
├── frontend/
├── backend/
└── packages/
    ├── parse_contracts/
    ├── parse_mcp/
    ├── parse_client_types/
    ├── parse_shared_utils/
    └── parse_linguistics_core/
```

### Expected Option-3 upgrades

1. Extract shared contracts/types from app code into packages.
2. Separate backend engine concerns into clearer service packages/modules.
3. Separate reusable linguistics/compute logic from transport/UI code.
4. Make agent-facing surfaces first-class packages rather than incidental wrappers.
5. Treat desktop shell as a stable app boundary, not just a convenience launcher.

---

## 7. Build-and-test-as-we-go rule

This plan explicitly requires **continuous parity testing during the rebuild**.

### 7.1 Principle

Do not “finish the rebuild and test later.”

Every major slice must be tested against the current PARSE behavior as it lands.

### 7.2 Required parity tracks

#### A. Frontend parity
For each rebuilt page or flow:
- compare current PARSE UI behavior vs rebuilt behavior
- check keyboard shortcuts
- verify mode/page transitions
- verify visible affordances and data loading

#### B. API/contract parity
For each rebuilt backend route:
- compare request/response shapes
- compare error semantics
- compare job lifecycle payloads
- compare export behavior

#### C. Workflow parity
For thesis-critical workflows:
- annotate load/edit/save
- compare load/decision flows
- tags and enrichments persistence
- export
- onboarding/import
- job status / progress / failure handling

### 7.3 Parity artifacts to maintain

The rebuild repo should keep a dedicated `parity/` directory for:
- shared fixtures and oracle baseline snapshots
- UI checklists and screenshots
- API contract snapshots/tests
- job traces/logs
- export comparisons/goldens
- known deviations with justification

---

## 8. Suggested phased roadmap

## Phase 0 — Planning + contracts

**Location:** current PARSE repo + rebuild repo bootstrap

Deliverables:
- plan-only PR in current PARSE repo
- rebuild repo scaffold
- `docs/plans/option1-parity-inventory.md` as the parity scope + evidence contract
- `docs/plans/option1-phase0-shared-contract-checklist.md` as the coordinator gate before parallel work
- initial parity checklist
- explicit contract inventory from current PARSE

## Phase 1 — Rebuild shell + core routes (Option 1 style)

Deliverables:
- rebuilt app shell in separate repo
- thin frontend shell structure
- thin backend route/service structure
- first parity tests against current PARSE

Targets:
- frontend shell/navigation
- basic project/config loading
- baseline route contracts
- desktop bootstrap handshake

## Phase 2 — Rebuild Annotate + Compare core workflows

Deliverables:
- rebuilt Annotate page
- rebuilt Compare page
- core backend support for both
- parity tests for save/load/compute/export-critical flows

Targets:
- replace dependence on giant `ParseUI.tsx`
- replace dependence on giant `server.py` route pile-up

## Phase 3 — Rebuild advanced compute / AI / agent surfaces

Deliverables:
- rebuilt job orchestration
- AI/chat/tool surfaces
- MCP/OpenAPI/streaming parity
- desktop hardening for local runtime

Targets:
- `chat_tools.py` decomposition
- route/service separation for advanced compute paths

### Phase 3 target structure (expected rebuild-repo shape by end of phase)

By the end of Phase 3, the separate rebuild repo should still be recognizably **Option 1**, but mature enough that the later Option-3 promotion is mostly packaging/boundary work rather than another rewrite.

```text
<rebuild-repo>/
├── desktop/
│   ├── electron-main/
│   ├── preload/
│   └── packaging/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── router.tsx
│   │   │   ├── layouts/
│   │   │   └── providers/
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── annotate/
│   │   │   ├── compare/
│   │   │   ├── compute/
│   │   │   ├── shell/
│   │   │   └── shared/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── lib/
│   │   └── workers/
│   └── tests/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── jobs/
│   │   ├── http/
│   │   ├── services/
│   │   └── bootstrap.py
│   ├── ai/
│   │   ├── chat/
│   │   ├── providers/
│   │   ├── stt/
│   │   ├── ipa/
│   │   └── workflow/
│   ├── compare/
│   │   ├── providers/
│   │   ├── cognates/
│   │   ├── offsets/
│   │   └── contact_lexemes/
│   ├── external_api/
│   ├── adapters/
│   ├── workers/
│   ├── shared/
│   └── tests/
├── parity/
│   ├── fixtures/
│   ├── contracts/
│   ├── ui/
│   │   ├── checklists/
│   │   └── screenshots/
│   ├── api/
│   │   ├── snapshots/
│   │   └── contract-tests/
│   ├── jobs/
│   ├── export/
│   └── deviations.md
└── docs/
```

### Why this Phase 3 structure matters
- the **desktop shell is already first-class**
- the **frontend shell and pages are separated from shared primitives**
- the **backend transport layer is already thinner than today's `server.py`**
- AI/compare domains are already decomposed enough to extract later into real packages
- parity assets remain explicit and continuously maintained during the rebuild

## Phase 4 — Promote toward Option 3

Deliverables:
- shared package extraction
- contract/type packages
- stronger separation between desktop/frontend/backend/packages
- deprecation strategy for the old repo/runtime

Targets:
- evolve rebuild repo from Option 1 implementation shape to Option 3 platform shape

---

## 9. Success criteria

This plan succeeds if:

1. The rebuilt app reaches usable parity with current PARSE while still in the separate repo.
2. Testing happens continuously during the rebuild, not only at the end.
3. The rebuilt app is clearly structured enough that Option 3 promotion is evolutionary rather than a second rewrite.
4. Current PARSE remains usable as the stable behavior oracle until the rebuild is genuinely ready.

---

## 10. Explicit non-goals for the first rebuild wave

- Do **not** try to convert the current PARSE repo directly into the final platform structure.
- Do **not** perform a one-shot repo-wide move to `frontend/`, `backend/`, and `packages/` in the current repo.
- Do **not** delay testing until the rebuild is “mostly complete.”
- Do **not** assume the final platform package boundaries before parity has been earned.

---

## 11. Recommended next actions after this plan PR

1. Approve the architecture decision: **separate rebuild repo now, Option 1 initially, Option 3 later**.
2. Create the rebuild repo.
3. Use `docs/plans/option1-parity-inventory.md` to freeze the parity scope for:
   - pages / workbenches
   - APIs
   - jobs
   - exports
   - desktop-critical constraints
4. Use `docs/plans/option1-phase0-shared-contract-checklist.md` to block Agent A / Agent B divergence until the shared contract is frozen.
5. Use `docs/plans/option1-two-agent-parallel-rebuild-plan.md` as the execution split for two main agents + subagents.
6. Start the rebuild with shell/bootstrap + parity harness first.

---

## 12. Bottom line

This plan intentionally separates:
- **where we build next** → a separate rebuild repo
- **how we build first** → Option 1
- **where we are going** → Option 3

That is the least risky path that still aligns with PARSE’s likely future as a desktop product and agent-accessible computational linguistics platform.
