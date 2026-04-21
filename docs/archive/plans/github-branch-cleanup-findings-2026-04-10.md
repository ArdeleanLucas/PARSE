# PARSE GitHub branch cleanup findings — 2026-04-10

> **Historical note (capture-time only):** this memo records the branch-cleanup recommendation state from 2026-04-10. Later cleanups landed, and the branch inventory continued to change after that pass. Treat all keep/delete guidance and branch counts below as historical evidence only; branch from `origin/main` for new work.

**Captured from:** `/home/lucas/gh/ardeleanlucas/parse`
**Docs branch for this memo:** `docs/parseui-planning` (historical; since deleted)
**Reference main:** `origin/main` @ `0fc397c`

## TLDR

- Delete the clearly merged or superseded remote branches.
- Keep `feat/parseui-unified-shell` and `docs/parseui-planning` as the rolling delivery branches.
- At capture time, do **not** delete `feat/annotate-ui-redesign` or `feat/parse-ai-connect-onboarding` yet; both were deleted in the later cleanup pass.
- Do **not** delete `docs/phase4-c5-c6-signoff` until PR #7 is resolved.
- `feat/compare-react` is safe to delete on GitHub, but local worktree cleanup should happen separately.

## Recommended remote deletions now

| Branch | Why it is safe to delete now |
| --- | --- |
| `docs/parsebuilder-todo-sync` | PR #14 merged. |
| `docs/phase0-repo-cleanup-preflight` | PR #4 merged. |
| `docs/phase2-compare-branch-audit` | PR #5 merged. |
| `docs/phase3-entrypoint-messaging` | PR #6 merged. |
| `docs/session-log-2026-04-10` | PR #23 merged. |
| `feat/annotate-react` | Historical track branch; no surviving delta vs `main`. Local worktree caveat only. |
| `feat/c5-export-lingpy-button` | PR #17 merged. |
| `feat/compare-react` | Prior audit plus current `git cherry` show no surviving code delta vs `main`. Local worktree caveat only. |
| `feat/mc-297-spectrogram-worker` | PR #11 merged. |
| `feat/mc-300-reference-forms` | PR #15 closed as superseded; `git cherry` shows the branch commit already subsumed by `main`. |
| `feat/mc-parseui-real-compare-data` | PR #12 merged. |
| `feat/parse-react-vite` | PR #2 merged; no remaining unique commits vs `main`. |
| `fix/mc-302-ai-connect-to-main` | PR #20 merged. |
| `fix/onboarding-open-ai-assistant` | PR #3 merged. |

## Keep as rolling branches

| Branch | Why keep it |
| --- | --- |
| `feat/parseui-unified-shell` | Canonical rolling code branch for ParseUI work targeting `main`. |
| `docs/parseui-planning` | Canonical rolling docs branch targeting `main`. |
| `main` | Protected trunk. |

## Historical "do not delete yet" set at capture time

| Branch | Reason |
| --- | --- |
| `docs/phase4-c5-c6-signoff` | PR #7 is still open. Resolve the PR first. |
| `feat/annotate-ui-redesign` | Historical note: PR #8 was closed, not merged; this branch was later deleted in the cleanup pass. |
| `feat/parse-ai-connect-onboarding` | Historical note: PR #19 merged into `feat/annotate-ui-redesign`, not into `main`; this branch was later deleted in the cleanup pass. |

## Historical follow-up that was recommended at capture time

1. Review `feat/annotate-ui-redesign` and `feat/parse-ai-connect-onboarding` together (this was later superseded by the cleanup pass that deleted both branches).
2. Cherry-pick or re-land anything still wanted onto `feat/parseui-unified-shell` (historical note: that rolling branch was later deleted after merge cleanup).
3. Only then delete those two remote branches.

## Local worktree caveat

`git worktree list` still shows:
- `feat/annotate-react`
- `feat/compare-react`

Recommendation:
- delete the **remote GitHub branches** now if approved,
- then do a separate local worktree cleanup pass so the attached local branches can be removed or repointed cleanly.

## Evidence snapshot used for this memo

- Open PRs observed:
  - PR #7 — `docs/phase4-c5-c6-signoff` -> `main` — still open
- Merged PRs observed for cleanup candidates:
  - PR #2, #3, #4, #5, #6, #11, #12, #14, #17, #20, #23
- Closed superseded PR observed:
  - PR #15 — `feat/mc-300-reference-forms`
- Branches that still carried commits not on `main` at capture time:
  - `feat/annotate-ui-redesign` (later deleted in the cleanup pass)
  - `feat/parse-ai-connect-onboarding` (later deleted in the cleanup pass)

## Recommended execution order

1. Merge or close PR #7.
2. At capture time: salvage any still-needed commits from `feat/annotate-ui-redesign` and `feat/parse-ai-connect-onboarding` (both were later deleted in the cleanup pass).
3. Delete the safe merged/superseded remote branches.
4. Run a separate local worktree cleanup pass.
