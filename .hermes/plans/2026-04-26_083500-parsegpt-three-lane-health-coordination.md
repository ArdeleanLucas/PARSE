# PARSE-rebuild — three-lane health coordination (2026-04-26)

## Purpose

This coordinator-owned note freezes the **current three-agent split** for PARSE-rebuild health work so Builder, parse-back-end, and parse-gpt can move in parallel **without file or PR collisions**.

This file is intentionally **coordination-only**. It does not redefine product architecture or claim parity. It records the live rebuild topology as of 2026-04-26 and names the current execution lanes.

---

## Repo and branch truth

- **Repo:** `TarahAssistant/PARSE-rebuild`
- **Canonical local path:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- **Remote default branch:** `origin/main`
- **Current `origin/main` head used for this note:** `2cd216c` (`refactor: extract job observability HTTP handlers (#12)`)

### Important local warning

The root checkout at `/home/lucas/gh/tarahassistant/PARSE-rebuild` is currently on a **stale local branch**:

- branch: `feat/parseui-shell-stage0-rebuild`
- remote tracking branch: **gone**

No new lane should branch from that root checkout. All new work should start from a clean `origin/main` worktree.

---

## Current open PRs

### Active implementation lanes

1. **Builder active lane**
   - PR #14
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/14`
   - head: `auto/parse-builder`
   - state at audit time: `DIRTY`
   - title: `feat: unify decisions persistence flows`

2. **parse-back-end active lane**
   - PR #13
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/13`
   - head: `auto/parse-back-end`
   - state at audit time: `CLEAN`
   - CI at audit time: green
   - title: `refactor: extract auth HTTP handlers`

3. **Older but still open Builder-adjacent implementation lane**
   - PR #11
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/11`
   - head: `refactor/parseui-stage2-offset-workflow`
   - state at audit time: `CLEAN`
   - CI at audit time: green
   - title: `refactor(parseui): extract stage2 offset workflow`

### Prompt / coordination PRs still open

4. **Builder prompt PR**
   - PR #5
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/5`
   - title: `docs: add parse-builder stage1 handoff prompt`

5. **parse-gpt prompt PR**
   - PR #6
   - URL: `https://github.com/TarahAssistant/PARSE-rebuild/pull/6`
   - title: `docs: add ParseGPT next external API slice prompt`

### Coordination interpretation

- PR #5 and PR #6 are **prompt/context artifacts**, not runtime health fixes.
- They may still be useful as briefing material for agents, but they should not be mistaken for the current implementation truth.
- PR #14 and PR #13 are the primary active lanes.
- PR #11 is relevant historical/adjacent implementation context for Builder, especially if PR #14 needs cleanup or re-basing.

---

## Current worktrees

### Main / reference worktrees

- `/home/lucas/gh/tarahassistant/PARSE-rebuild`
  - branch: `feat/parseui-shell-stage0-rebuild`
  - warning: stale local branch, gone remote

- `/home/lucas/gh/worktrees/PARSE-rebuild/job-observability-http-slice`
  - branch: `main`
  - purpose: clean main worktree

### Agent / lane worktrees

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-back-end-auto`
  - branch: `auto/parse-back-end`
  - active backend lane

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-stage2-prompt`
  - branch: `refactor/parseui-stage2-offset-workflow`
  - Builder-adjacent implementation context

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-builder-auto`
  - detached at `origin/main`
  - reusable if Builder wants a fresh clean worktree

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-gpt-auto`
  - branch: `auto/parse-gpt`
  - parse-gpt lane, currently behind `origin/main`

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-gpt-three-lane-health`
  - branch: `docs/parsegpt-three-lane-health-coordination`
  - **this coordinator lane**

### Older prompt / slice worktrees still present

- `/home/lucas/gh/worktrees/PARSE-rebuild/parse-back-end-prompt`
- `/home/lucas/gh/worktrees/PARSE-rebuild/parsegpt-next-external-api-prompt`
- `/home/lucas/gh/worktrees/PARSE-rebuild/refactor-external-api-http-slice`
- `/tmp/parse-rebuild-audit-main`

These are context-bearing, but they are not the authoritative active lanes unless explicitly reactivated.

---

## Lane ownership for the current health push

## Lane A — Builder

### Primary PR
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/14`

### Secondary context
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/11`
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/5`

### Scope
Builder owns **frontend/shared-shell/docs-adjacent** health work that does **not** collide with backend runtime repairs. Examples:
- decisions persistence unification
- ParseUI / shell / state coherence
- built-app UI smoke issues that are frontend-owned
- rebuild docs/process cleanup only where directly tied to Builder-owned surfaces

### Builder must not touch
- backend auth/MCP/ORTH runtime logic
- backend pytest root-cause repairs assigned to parse-back-end
- coordinator-owned merge sequencing / PR triage docs in this lane without explicit handoff

---

## Lane B — parse-back-end

### Primary PR
- `https://github.com/TarahAssistant/PARSE-rebuild/pull/13`

### Scope
parse-back-end owns **backend repo health** and server-side repairs, including the issues surfaced by the health audit:
- full backend pytest failures
- singleton/test contamination affecting MCP HTTP bridge tests
- ORTH config/runtime/test/docs contract alignment where runtime truth is backend-owned
- backend-side fixes needed to make the health audit pass cleanly

### parse-back-end must not touch
- Builder-owned decisions/shell/UI refactors
- coordinator-only PR triage / lane-mapping artifacts unless explicitly asked

---

## Lane C — parse-gpt / coordinator

### Primary PR
- **this PR** (coordination-only lane)

### Scope
parse-gpt owns:
- lane mapping
- merge sequencing recommendations
- stale prompt PR interpretation / close-later guidance
- integration verification planning after Builder + parse-back-end move
- any follow-up audit notes that help prevent overlap

### parse-gpt must not touch in this lane
- Builder implementation files
- backend implementation files
- shared runtime code unless a separate, explicitly scoped implementation PR is opened

---

## Immediate non-overlap rules

1. **No lane branches from the stale root checkout.**
2. **Builder and parse-back-end do not both edit the same functional surface in the same cycle.**
3. **Prompt PRs (#5, #6) are context only unless promoted by explicit merge/close decisions.**
4. **If Builder needs a fresh base, prefer a new branch from clean `origin/main` rather than mutating the stale root lane.**
5. **If parse-back-end lands health fixes that affect Builder assumptions, coordinator records the contract shift before Builder rebases.**

---

## Recommended near-term merge/decision order

This is not a final merge order, only the current health-oriented recommendation.

1. **parse-back-end / PR #13**
   - cleaner lane
   - green CI at audit time
   - backend health work is a prerequisite for a trustworthy rebuild baseline

2. **Builder / PR #14**
   - only after either:
     - it becomes clean/mergeable on its own, or
     - Builder rebases/repairs it based on current `main`

3. **Reassess PR #11**
   - merge only if it still carries unique value not subsumed by PR #14 or later Builder work

4. **Close or archive prompt PRs #5 and #6 later**
   - after the active implementation lanes no longer depend on them as human briefing context

---

## Stop / escalate conditions

Escalate to coordinator before continuing if any lane hits one of these:

- Builder needs to change backend route semantics
- parse-back-end needs to change frontend store/client assumptions
- PR #14 and PR #11 are discovered to overlap in a way that makes both merge targets incoherent
- a lane wants to merge a prompt-only PR as if it were implementation work
- a lane discovers that the worktree/PR mapping above is stale

---

## Deliverable expectation for each agent

Every lane should report:
1. PR number + URL
2. worktree path used
3. branch used
4. files changed
5. validations run
6. what was intentionally left for another lane

That report format is mandatory because the human coordination model here is **copy/paste PR URLs**, not free-form local summaries.
