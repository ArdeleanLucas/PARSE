# PARSE branch cleanup delete commands — 2026-04-21

> Snapshot memo generated from the canonical active repo: `/home/lucas/gh/ardeleanlucas/parse`
>
> Reference trunk at capture time: `origin/main` = `13d16b2cba8daf747cf8e9ca8701f9dd169b16c9`
>
> This memo is intentionally command-oriented. It does **not** authorize blind deletion later if branch state changes; re-run the short preflight first.

## Purpose

Provide the exact validated commands for pruning the currently stale PARSE branches in the **canonical lowercase repo**. These commands are grounded in the re-check performed after `origin/main` advanced through PR #76.

## Re-verify before deleting anything

Run this first. If the branch list no longer matches this memo, stop and re-audit instead of executing stale commands.

```bash
git -C /home/lucas/gh/ardeleanlucas/parse fetch origin --prune

gh api repos/ArdeleanLucas/PARSE/branches --paginate --jq '.[].name' | sort

git -C /home/lucas/gh/ardeleanlucas/parse branch -vv
git -C /home/lucas/gh/ardeleanlucas/parse worktree list
```

Expected remote branch list at capture time:

```text
docs/generalize-beyond-sk
feat/chat-context-ring
feat/chat-tool-reference-forms
feat/dark-mode-noir-styles
feat/job-eta
feat/mcp-server
feat/parse-run-script
fix/chat-xai-fetch-failure
fix/dark-mode-chat-and-amber
fix/mc-315-grok-reasoning-effort
fix/mc-316-codex-auth-connectivity
fix/openai-auth-double-import
main
```

## 1) Safe remote GitHub branch deletion

All 12 non-`main` remote branches below were re-verified as merged leftovers:
- `git rev-list --left-right --count origin/main...origin/<branch>` → right side `0`
- `git cherry -v origin/main origin/<branch>` → empty
- `git merge-base --is-ancestor origin/<branch> origin/main` → success

Exact command:

```bash
git -C /home/lucas/gh/ardeleanlucas/parse push origin --delete \
  docs/generalize-beyond-sk \
  feat/chat-context-ring \
  feat/chat-tool-reference-forms \
  feat/dark-mode-noir-styles \
  feat/job-eta \
  feat/mcp-server \
  feat/parse-run-script \
  fix/chat-xai-fetch-failure \
  fix/dark-mode-chat-and-amber \
  fix/mc-315-grok-reasoning-effort \
  fix/mc-316-codex-auth-connectivity \
  fix/openai-auth-double-import
```

## 2) Safe local merged-branch deletion in the canonical repo

First move the canonical checkout off `feat/mcp-server` and fast-forward local `main`.

```bash
git -C /home/lucas/gh/ardeleanlucas/parse fetch origin --prune
git -C /home/lucas/gh/ardeleanlucas/parse switch main
git -C /home/lucas/gh/ardeleanlucas/parse pull --ff-only origin main
```

Then delete the merged local branches that are already fully subsumed by `origin/main`.

```bash
git -C /home/lucas/gh/ardeleanlucas/parse branch -d \
  feat/chat-tool-reference-forms \
  feat/mcp-server \
  fix/auth-key-read-body \
  fix/chat-xai-fetch-failure \
  fix/mc-313-openai-codex-auth \
  fix/mc-315-grok-reasoning-effort \
  fix/mc-316-codex-auth-connectivity \
  fix/xai-chat-integration \
  pr-49-review
```

## 3) Worktree-blocked local branches

These branches can be removed locally only after their attached worktrees are removed.

Remove the worktrees:

```bash
git -C /home/lucas/gh/ardeleanlucas/parse worktree remove /tmp/parse-stage3-impl
git -C /home/lucas/gh/ardeleanlucas/parse worktree remove /tmp/parse-stage3-preflight
git -C /home/lucas/gh/ardeleanlucas/parse worktree remove /tmp/parse-pr53-review
```

Then delete the corresponding local branches:

```bash
git -C /home/lucas/gh/ardeleanlucas/parse branch -d \
  chore/remove-vanilla-js-stage3 \
  docs/stage3-preflight-c5-c6

git -C /home/lucas/gh/ardeleanlucas/parse branch -D docs/audit-2026-04-20
```

Why `-D` for `docs/audit-2026-04-20`:
- its upstream is already gone
- it is a closed audit branch with local-only history
- it is not a clean ancestor of current `origin/main`
- deletion is still reasonable if Lucas no longer wants the audit snapshot locally

## 4) Optional local review/snapshot branch deletion

These are not part of the default merged-branch cleanup, but they are typical stale local-only review or snapshot branches.

### 4a) Optional force-delete closed review snapshots

```bash
git -C /home/lucas/gh/ardeleanlucas/parse branch -D \
  pr-52-review \
  pr-53-review \
  pr-7-review \
  pr-70-review
```

### 4b) Optional force-delete doc/snapshot leftovers if no archival value remains

```bash
git -C /home/lucas/gh/ardeleanlucas/parse branch -D \
  docs/fix-openai-codex-auth-plan \
  docs/update-task-list \
  backup/chore-remove-vanilla-js-stage3-pre-rebase-20260420 \
  backup/feat-chat-tool-reference-forms-pre-rebase-20260420
```

## 5) Deliberately excluded from the default cleanup command set

These are **not** included above on purpose:
- the uppercase archival clone: `/home/lucas/gh/ArdeleanLucas/PARSE`
- its historical worktree branches such as `feat/annotate-react`, `feat/compare-react`, and `feat/parse-react-vite`

Reason: the uppercase clone is not current branch truth and should be handled in a separate archival cleanup pass.

## 6) Post-cleanup verification

After any cleanup run, re-check refs and then run the standard PARSE validation gate on trunk.

```bash
git -C /home/lucas/gh/ardeleanlucas/parse fetch origin --prune
git -C /home/lucas/gh/ardeleanlucas/parse branch -vv
git -C /home/lucas/gh/ardeleanlucas/parse worktree list
gh api repos/ArdeleanLucas/PARSE/branches --paginate --jq '.[].name' | sort

cd /home/lucas/gh/ardeleanlucas/parse
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

## Evidence summary behind this memo

Validated again at capture time from `/home/lucas/gh/ardeleanlucas/parse`:
- current `origin/main`: `13d16b2cba8daf747cf8e9ca8701f9dd169b16c9`
- current live GitHub non-`main` remote branches: 12
- all 12 remote branches above had `branch-only commits = 0` vs `origin/main`
- all 12 remote branches above had empty `git cherry` output vs `origin/main`
- local merged-delete set above had no surviving cherry commits vs `origin/main`
- local review/audit snapshot branches needing `-D` were kept separate from the safe merged-delete command set
