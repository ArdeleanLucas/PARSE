# PARSE Worktree Setup — Multi-Agent Parallel Development

**Purpose:** Give PARSE agents isolated checkouts of the canonical repository while treating `origin/main` as the only base for new work.

## Canonical Repo

`https://github.com/ArdeleanLucas/PARSE`

- **Source of truth:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
  - The directory name is historical after the 2026-04-27 cutover.
  - `git remote -v` must show `origin git@github.com:ArdeleanLucas/PARSE.git` before any work.
  - Do not use `/home/lucas/gh/ardeleanlucas/parse` or `/home/lucas/gh/ArdeleanLucas/PARSE` as branch truth; those duplicate/pre-cutover clones are not the active checkout on this workstation.

---

## Directory Layout

```text
/home/lucas/gh/tarahassistant/PARSE-rebuild/    ← canonical clone on `main`
/home/lucas/gh/worktrees/<branch-slug>/          ← optional isolated worktree per branch from `origin/main`
```

Each worktree shares the git object store from the canonical clone.

---

## Setup Commands

Prefer Lucas's local helper when it is available:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --quiet --prune
parse-worktree-new <branch-slug>
```

Manual equivalent:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --quiet --prune
git switch main
git reset --hard origin/main

git worktree add /home/lucas/gh/worktrees/<branch-slug> \
  -b <branch-name> origin/main

git worktree list
```

---

## Agent Assignment

| Agent | Checkout | Branch policy | MESSAGING_CWD |
|---|---|---|---|
| `parse-front-end` | dedicated worktree under `/home/lucas/gh/worktrees/<slug>/` | branch from `origin/main`; PR to `ArdeleanLucas/PARSE` | set to that worktree path |
| `parse-back-end` | dedicated worktree under `/home/lucas/gh/worktrees/<slug>/` | branch from `origin/main`; PR to `ArdeleanLucas/PARSE` | set to that worktree path |
| `parse-coordinator` | canonical clone for docs/handoffs, or dedicated docs worktree when safer | branch from `origin/main`; PR to `ArdeleanLucas/PARSE` | current coordinator checkout |

Example Hermes config:

```yaml
MESSAGING_CWD: /home/lucas/gh/worktrees/feat-example
```

Each agent edits only its own checkout. Use `gh pr create --repo ArdeleanLucas/PARSE --base main ...` explicitly; do not rely on implicit `gh` remote inference.

---

## Current shipped feature-lane note

The concept-scoped pipeline contract in [`concept-scoped-pipeline.md`](concept-scoped-pipeline.md) is now shipped on `main` via PR #190/#193 (contract/docs), PR #191 (frontend), PR #192 (backend/MCP), and PR #196 (ORTH/STT language-safety follow-up). New work should treat `run_mode` and `affected_concepts` as current contract, not an active unmerged lane.

---

## Merge Strategy

1. Start every new branch from current `origin/main`.
2. Give each implementation agent its own worktree / branch.
3. Open PRs back to `main` on `ArdeleanLucas/PARSE` (submit only — Lucas merges).
4. Refetch before reporting PR mergeability.
5. Delete temporary worktrees once the PR is merged or abandoned.
