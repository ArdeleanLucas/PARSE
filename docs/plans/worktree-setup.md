# PARSE Worktree Setup — Multi-Agent Parallel Development

**Purpose:** Give multiple PARSE agents isolated checkouts of the same repository with no file conflicts while treating `origin/main` as the only base for new work.

## Canonical Repo

`https://github.com/ArdeleanLucas/PARSE`

- **Source of truth:** `/home/lucas/gh/ardeleanlucas/parse` (lowercase clone, tracks `origin/main`)

---

## Directory Layout

```text
/home/lucas/gh/ardeleanlucas/
  parse/                       ← canonical clone on `main`
/home/lucas/gh/worktrees/parse/
  <branch-name>/               ← optional worktree per new branch from `origin/main`
```

Each worktree shares the git object store from the canonical clone.

---

## Setup Commands

```bash
# 1. Clone the canonical repo once
cd /home/lucas/gh/ardeleanlucas
git clone https://github.com/ArdeleanLucas/PARSE parse
cd parse

git fetch origin --prune
git switch main

# 2. Create a worktree root for new branches
mkdir -p /home/lucas/gh/worktrees/parse

# 3. Create a worktree from origin/main for a new branch
git worktree add /home/lucas/gh/worktrees/parse/<branch-slug> \
  -b <branch-name> origin/main

# 4. Verify
git worktree list
```

---

## Agent Assignment

| Agent | Checkout | Branch policy | MESSAGING_CWD |
|---|---|---|---|
| Any PARSE agent | dedicated worktree under `/home/lucas/gh/worktrees/parse/` | branch from `origin/main` | set to that worktree path |

Example Hermes config:

```yaml
MESSAGING_CWD: /home/lucas/gh/worktrees/parse/feat-example
```

Each agent edits only its own checkout.

Active feature-lane contract: [`concept-scoped-pipeline.md`](concept-scoped-pipeline.md) coordinates the current backend, frontend, and coordinator lanes for concept-windowed / edited-only pipeline reruns.

---

## Merge Strategy

1. Start every new branch from `origin/main`.
2. Give each agent its own worktree / branch.
3. Open PRs back to `main` (submit only — Lucas merges).
4. Delete temporary worktrees once the PR is merged or abandoned.
