# PARSE-rebuild — three-lane health coordination (2026-04-26)

## Purpose

This coordinator-owned note freezes the current three-agent split for PARSE-rebuild health work so Builder, parse-back-end, and parse-gpt can move in parallel without file or PR collisions.

This file is intentionally coordination-only. It does not redefine product architecture or claim parity. It records the live rebuild topology **after merged PR #13 and closed PR #16**.

---

## Repo and branch truth

- **Repo:** `TarahAssistant/PARSE-rebuild`
- **Canonical local path:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- **Remote default branch:** `origin/main`
- **Current `origin/main` head used for this note:** `4ed1eb7` (`refactor: extract auth HTTP handlers (#13)`)

### Important local warning

The root checkout at `/home/lucas/gh/tarahassistant/PARSE-rebuild` is still on a stale local branch:
- branch: `feat/parseui-shell-stage0-rebuild`
- remote tracking branch: gone

No new lane should branch from that root checkout. All new work should start from a clean `origin/main` worktree.

---

## Current PR topology

### Open implementation PRs

1. **Builder implementation lane**
   - PR #14
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/14`
   - head: `auto/parse-builder`
   - title: `feat: unify decisions persistence flows`
   - note: active implementation PR; Builder should not widen it with unrelated crash-fix work

2. **Older Builder-adjacent implementation lane**
   - PR #11
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/11`
   - head: `refactor/parseui-stage2-offset-workflow`
   - title: `refactor(parseui): extract stage2 offset workflow`
   - note: still open; treat as historical/adjacent implementation context until explicitly merged or closed

### Open prompt / coordination PRs

3. **parse-gpt coordination PR**
   - PR #15
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/15`
   - head: `docs/parsegpt-three-lane-health-coordination`
   - title: `docs: add three-lane health coordination note`

4. **Builder next-task prompt**
   - PR #17
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/17`
   - head: `docs/parse-builder-next-task-transcription-lanes-crash-v2`
   - title: `docs: refresh parse-builder next task prompt`
   - note: current Builder handoff prompt; supersedes stale PR #16

5. **parse-back-end next-task prompt**
   - PR #18
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/18`
   - head: `docs/parse-back-end-next-task-backend-health-v1`
   - title: `docs: add parse-back-end next task prompt`
   - note: current backend handoff prompt after PR #13 merged

6. **Older parse-gpt prompt PR**
   - PR #6
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/6`
   - title: `docs: add ParseGPT next external API slice prompt`

7. **Older test prompt/implementation PR**
   - PR #2
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/2`
   - title: `test(parseui): add stage0 shell regression coverage`

### Closed or merged context that matters right now

- **PR #13** — merged
  - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/13`
  - merge commit now on `main`: `4ed1eb7`
- **PR #16** — closed as stale
  - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/16`
  - reason: it described live topology incorrectly once PR #13 merged
- **PR #5** — stale Builder prompt context
  - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/5`
  - no longer safe as live Builder guidance

### Coordination interpretation

- PR #14 is the only clearly active Builder implementation PR.
- parse-back-end currently has **no open implementation PR**; its next move is defined by prompt PR #18.
- PR #17 and PR #18 are handoff/context PRs, not implementation results.
- PR #6 and PR #5 are historical prompt artifacts.
- PR #11 remains an open implementation-context artifact that must be considered in merge/resequence decisions.

---

## Current worktrees

### Main / reference worktrees

- `/home/lucas/gh/tarahassistant/PARSE-rebuild`
  - branch: `feat/parseui-shell-stage0-rebuild`
  - warning: stale local branch, gone remote

- `/home/lucas/gh/worktrees/PARSE-rebuild/job-observability-http-slice`
  - branch: `main`
  - note: local `main` worktree exists but is behind remote by one merged commit unless refreshed

### Agent / lane worktrees

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto`
  - detached at old `origin/main` snapshot
  - reusable only after explicit refresh/reset

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-stage2-prompt`
  - branch: `refactor/parseui-stage2-offset-workflow`
  - ties to PR #11

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-back-end-auto`
  - detached at merged PR #13 commit `4ed1eb7`
  - previous backend implementation worktree; no active backend feature branch attached now

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-gpt-three-lane-health`
  - branch: `docs/parsegpt-three-lane-health-coordination`
  - this coordinator lane / PR #15

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-gpt-builder-next-task-v2`
  - branch: `docs/parse-builder-next-task-transcription-lanes-crash-v2`
  - Builder handoff PR #17

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-gpt-backend-next-task`
  - branch: `docs/parse-back-end-next-task-backend-health-v1`
  - parse-back-end handoff PR #18

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-gpt-auto`
  - branch: `auto/parse-gpt`
  - behind current `origin/main`

### Older prompt / review worktrees still present

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-back-end-prompt`
- `/home/lucas/gh/worktrees/PARSE-rebuild/parsegpt-next-external-api-prompt`
- `/home/lucas/gh/worktrees/PARSE-rebuild/refactor-external-api-http-slice`
- `/tmp/parse-rebuild-audit-main`
- `/tmp/parse-rebuild-pr16-review`
- `/tmp/parse-rebuild-pr3-review`
- `/tmp/parse-rebuild-pr5-review`

These are context-bearing only. They are not authoritative active lanes unless explicitly reactivated.

---

## Lane ownership for the current health push

## Lane A — Builder

### Primary implementation PR
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/14`

### Current handoff PR
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/17`

### Secondary context
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/11`
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/5`

### Scope
Builder owns frontend/shared-shell health work that does not collide with backend runtime repairs. Current queued Builder bugfix work is the Compare → Annotate `TranscriptionLanes` hook-order crash, explicitly separated from PR #14.

### Builder must not touch
- backend MCP/ORTH/runtime fixes
- backend full-suite pytest repairs
- coordinator-only PR topology docs unless explicitly asked

---

## Lane B — parse-back-end

### Current handoff PR
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/18`

### Scope
parse-back-end owns backend repo health and server-side repairs. Current queued backend work is:
- make the full backend suite green on current `main`
- fix MCP HTTP bridge singleton/test contamination in the full run
- reconcile ORTH runtime/test/config/example-config contract drift

### parse-back-end must not touch
- Builder’s `TranscriptionLanes` hook-order crash
- decisions persistence UI work in PR #14
- coordinator-only PR topology docs unless explicitly asked

---

## Lane C — parse-gpt / coordinator

### Primary PR
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/15`

### Scope
parse-gpt owns:
- lane mapping
- resequencing after merges/closures
- stale prompt replacement
- integration verification planning after Builder + parse-back-end move
- keeping the PR/worktree map current enough that future handoffs do not immediately stale out

### parse-gpt must not touch in this lane
- Builder implementation files
- backend implementation files
- shared runtime code unless a separate implementation PR is intentionally opened

---

## Immediate non-overlap rules

1. No lane branches from the stale root checkout.
2. Builder and parse-back-end do not both edit the same functional surface in the same cycle.
3. Prompt PRs are not implementation and should not be merged as runtime truth without checking freshness.
4. If Builder needs a fresh execution base, start from current `origin/main`, not the stale root or old detached builder worktree.
5. If parse-back-end opens a new implementation PR from handoff PR #18, coordinator should record the new URL before issuing any further cross-lane handoffs.

---

## Recommended near-term sequence

This is not a final merge order; it is the current coordination recommendation.

1. **Builder acts on PR #17 guidance**
   - open a fresh implementation PR for the Compare → Annotate `TranscriptionLanes` hook-order crash
   - keep PR #14 separate

2. **parse-back-end acts on PR #18 guidance**
   - open a fresh implementation PR for the current backend suite failures
   - do not reopen PR #13

3. **Reassess PR #14 and PR #11 once the crash fix and backend suite fix are underway or landed**
   - decide whether #11 still carries unique value
   - decide whether #14 needs rebase/cleanup before merge

4. **Close stale prompt artifacts later**
   - PR #5 and PR #6 are historical prompt context, not active runtime truth

---

## Stop / escalate conditions

Escalate to coordinator before continuing if any lane hits one of these:
- Builder needs to change backend route semantics
- parse-back-end needs to change frontend store/client assumptions
- PR #14 and PR #11 are found to overlap in a way that makes both merge targets incoherent
- a prompt PR is about to be treated as durable implementation state without freshness verification
- the worktree/PR mapping above becomes stale again because a new PR merged or closed

---

## Deliverable expectation for each agent

Every lane should report:
1. PR number + URL
2. worktree path used
3. branch used
4. files changed
5. validations run
6. what was intentionally left for another lane

That reporting format is mandatory because the human coordination model here is copy/paste PR URLs, not free-form local summaries.
