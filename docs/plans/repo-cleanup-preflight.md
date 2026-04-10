# PARSE Repo Cleanup Preflight

**Purpose:** Capture the minimum factual state needed before any destructive repo cleanup, branch deletion, or legacy frontend removal.

**Captured on:** 2026-04-09
**Active repo:** `/home/lucas/gh/ardeleanlucas/parse`
**Active branch when captured:** `docs/phase0-repo-cleanup-preflight`

> **Historical note (post-cleanup):** this preflight captured the repo before the later branch-pruning pass. Treat branch lists here as historical snapshots. Current work should branch from `origin/main`, and the remote is now down to 4 branches.

---

## 1. Current `origin/main`

- **`origin/main` SHA:** `3ab3be5541db7892a7e13b9c5aec062fb23b4c53`
- **Meaningful recent merges on `main`:**
  - PR #3 — onboarding fix merged
  - PR #1 — config/onboarding fixes merged
  - PR #2 — `feat/parse-react-vite` integration merged earlier in the line

---

## 2. Current remote branch list

- `origin/main`
- `origin/feat/annotate-react`
- `origin/feat/compare-react`
- `origin/feat/parse-react-vite`
- `origin/fix/onboarding-open-ai-assistant`

---

## 3. Branch ancestry / ahead-behind facts

### `origin/feat/annotate-react`
- Ahead vs `origin/main`: `0`
- Behind vs `origin/main`: `31`
- Branch-only commits relative to `origin/main`: none
- Working classification: **cleanly subsumed historical branch**
- Implication: safe deletion candidate once Lucas approves branch pruning

### `origin/feat/parse-react-vite`
- Ahead vs `origin/main`: `0`
- Behind vs `origin/main`: `9`
- Branch-only commits relative to `origin/main`: none
- Working classification: **cleanly subsumed integration branch**
- Implication: safe deletion candidate once Lucas approves branch pruning

### `origin/fix/onboarding-open-ai-assistant`
- Ahead vs `origin/main`: `0`
- Behind vs `origin/main`: `1`
- Branch-only commits relative to `origin/main`: none
- Working classification: **cleanly subsumed landed fix branch**
- Implication: safe deletion candidate once Lucas approves branch pruning

### `origin/feat/compare-react`
- Ahead vs `origin/main`: `1`
- Behind vs `origin/main`: `8`
- Branch-only commit(s):
  - `b8ecd1e` — `merge: config+auth fixes (MC-281) into feat/compare-react`
- Working classification: **ambiguous / not a clean ancestor**
- Implication: **do not delete blindly**; requires explicit audit and Lucas decision

---

## 4. Uppercase clone warning

Secondary clone:
- `/home/lucas/gh/ArdeleanLucas/PARSE`

Known state from prior audit:
- its local `main` points at `archive/main`
- it diverges heavily from `origin/main`
- it is not a safe basis for branch truth or cleanup decisions without an explicit Lucas-approved repoint/reset

Implication:
- destructive cleanup decisions should be based on the lowercase active repo plus GitHub remote state, not the uppercase clone

---

## 5. Rollback recommendations

### Before any branch deletions
Recommended safety step:
- capture the current remote branch list and corresponding SHAs in a PR comment or audit note
- if Lucas wants an extra hedge, create local backup refs before deletion, e.g.:
  - `backup/feat-annotate-react-<date>`
  - `backup/feat-parse-react-vite-<date>`
  - `backup/fix-onboarding-open-ai-assistant-<date>`

### Before any C7 destructive cleanup
Recommended safety step:
- create a visible rollback point on the current `main`, e.g.:
  - annotated tag: `pre-c7-legacy-removal`
  - or backup branch: `backup/pre-c7-legacy-removal`
- ensure the PR description records:
  - `origin/main` SHA before deletion
  - list of deleted files
  - any launcher/server behavior changed

### Before touching the uppercase clone
Recommended safety step:
- decide whether it is archival and should remain untouched
- if Lucas wants it repointed, record current `archive/main` SHA before any reset

---

## 6. Preflight go / no-go summary

### Go now
- non-destructive docs/policy reconciliation
- legacy reference inventory
- compare-branch audit
- non-destructive README/server messaging PRs

### No-go until Lucas decision/signoff
- branch deletions
- uppercase clone reset/repoint
- legacy frontend removal (`parse.html`, `compare.html`, `js/`)
- Python-server frontend cutover to built React app

### No-go until C5 + C6 cleared
- any C7 destructive cleanup or canonical frontend cutover
