# PARSE Worktree Setup — Multi-Agent Parallel Development

**Purpose:** Give ParseBuilder and parse-gpt isolated checkouts of the same repo with no file conflicts.

## Repo

`https://github.com/ArdeleanLucas/PARSE` (new canonical home)

---

## Directory Layout

```
/home/lucas/gh/ardeleanlucas/
  PARSE/                       ← primary clone (main branch, bare reference)
    .git/                      ← shared git object store
  PARSE-parse-builder/         ← ParseBuilder worktree (feat/parse-react-vite)
  PARSE-parse-gpt/             ← parse-gpt worktree  (feat/parse-gpt or new feat branches)
```

Each worktree shares `.git/` from `PARSE/` — no duplication of history or objects.

---

## Setup Commands (run once after repo is created on GitHub)

```bash
# 1. Clone the new repo as primary
cd /home/lucas/gh/ardeleanlucas
git clone https://github.com/ArdeleanLucas/PARSE PARSE
cd PARSE

# 2. ParseBuilder worktree — feat/parse-react-vite (all Phase C + CLEF work)
git worktree add ../PARSE-parse-builder feat/parse-react-vite

# 3. parse-gpt worktree — new branch for its tasks
git worktree add ../PARSE-parse-gpt -b feat/parse-gpt-work

# 4. Verify
git worktree list
```

---

## Agent Assignment

| Agent | Worktree | Branch | MESSAGING_CWD |
|---|---|---|---|
| ParseBuilder (you) | `/home/lucas/gh/ardeleanlucas/PARSE-parse-builder` | `feat/parse-react-vite` | N/A (Discord) |
| parse-gpt | `/home/lucas/gh/ardeleanlucas/PARSE-parse-gpt` | `feat/parse-gpt-work` | Set to worktree path |

---

## parse-gpt Gateway Config

In parse-gpt's Hermes config, set:
```yaml
MESSAGING_CWD: /home/lucas/gh/ardeleanlucas/PARSE-parse-gpt
```

This ensures parse-gpt's file edits, terminal commands, and context files all land in its own worktree — never touching ParseBuilder's working files.

---

## Merge Strategy

1. Both agents commit + push to their own branches
2. ParseBuilder leads Phase C integration merges (unchanged from current plan)
3. PRs: each agent's branch → `main` via Lucas review
4. No direct pushes to `main`

---

## What parse-gpt Can Work On (suggested)

Since `feat/parse-react-vite` is mid-Phase C (C5/C6 pending Lucas browser check, C7 cleanup next), parse-gpt can start:
- Phase D work in its own branch: deploy workflow, PARSE server bundling, Electron packaging
- Or any of the contact lexeme pipeline tasks that don't conflict with Phase C

Coordinate via Discord before touching shared files (server.py, enrichments schema).
