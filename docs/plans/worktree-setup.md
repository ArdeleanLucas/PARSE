# PARSE Worktree Setup — Multi-Agent Parallel Development

**Purpose:** Give multiple PARSE agents isolated checkouts of the same repository with no file conflicts while treating `origin/main` as the only base for new work.

## Canonical Repo

`https://github.com/ArdeleanLucas/PARSE`

- **Source of truth:** `/home/lucas/gh/ardeleanlucas/parse`
- **Archive/divergent clone:** `/home/lucas/gh/ArdeleanLucas/PARSE` (do **not** use this as branch truth)

> **Historical note:** older plans referenced `feat/parse-react-vite`, `feat/parseui-unified-shell`, and `docs/parseui-planning` as rolling branches. Those branches have been merged and deleted. Do not recreate them; branch from `origin/main` instead.

---

## Directory Layout

```text
/home/lucas/gh/ardeleanlucas/
  parse/                       ← canonical clone on `main`
/home/lucas/gh/worktrees/parse/
  <branch-name>/               ← optional worktree for a new branch from `origin/main`
/home/lucas/gh/ArdeleanLucas/PARSE/
  ...                          ← archival/divergent clone; traceability only
```

Each worktree shares the git object store from the canonical lowercase clone.

---

## Setup Commands (current workflow)

```bash
# 1. Clone the canonical repo once
cd /home/lucas/gh/ardeleanlucas
git clone https://github.com/ArdeleanLucas/PARSE parse
cd parse

git fetch origin --prune
git switch main

# 2. Create a worktree root for new branches
mkdir -p /home/lucas/gh/worktrees/parse

# 3. Create an example docs worktree from origin/main
git worktree add /home/lucas/gh/worktrees/parse/docs-stale-branch-reference-cleanup \
  -b docs/stale-branch-reference-cleanup origin/main

# 4. Create an example feature worktree from origin/main
git worktree add /home/lucas/gh/worktrees/parse/feat-example \
  -b feat/example origin/main

# 5. Verify
git worktree list
```

---

## Agent Assignment

| Agent | Recommended checkout | Branch policy | MESSAGING_CWD |
|---|---|---|---|
| ParseBuilder | `/home/lucas/gh/ardeleanlucas/parse` or a dedicated worktree | branch from `origin/main` | N/A (Discord) |
| parse-gpt | dedicated worktree under `/home/lucas/gh/worktrees/parse/` | branch from `origin/main` | set to that worktree path |

Example Hermes config:

```yaml
MESSAGING_CWD: /home/lucas/gh/worktrees/parse/feat-example
```

This ensures each agent edits only its own checkout.

---

## Merge Strategy

1. Start every new branch from `origin/main`.
2. Give each agent its own worktree / branch.
3. Open PRs back to `main`.
4. Do not use the uppercase archival clone for branch conclusions.
5. Delete temporary worktrees once the PR is merged or abandoned.

---

## Historical Worktrees

These may still exist locally for traceability:
- `/home/lucas/gh/worktrees/PARSE/annotate-react`
- `/home/lucas/gh/worktrees/PARSE/compare-react`

Treat them as historical lanes, not the default basis for new work.
