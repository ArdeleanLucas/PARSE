# PARSE GitHub branch cleanup findings — 2026-04-10

> **Historical note (post-cleanup):** the GitHub cleanup described here has since landed. `origin` now exposes only 4 remote branches (`main`, `docs/phase4-c5-c6-signoff`, `feat/annotate-react`, `feat/compare-react`), and the rolling branches named below (`feat/parseui-unified-shell`, `docs/parseui-planning`) were later merged/deleted. Keep this memo as historical evidence only; branch from `origin/main` for new work.

**Captured from:** `/home/lucas/gh/ardeleanlucas/parse`
**Docs branch for this memo:** `docs/parseui-planning` (historical; since deleted)
**Reference main:** `origin/main` @ `0fc397c`

## TLDR

- Delete the clearly merged or superseded remote branches.
- Keep `feat/parseui-unified-shell` and `docs/parseui-planning` as the rolling delivery branches.
- Do **not** delete `feat/annotate-ui-redesign` or `feat/parse-ai-connect-onboarding` yet.
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

## Do not delete yet

| Branch | Reason |
| --- | --- |
| `docs/phase4-c5-c6-signoff` | PR #7 is still open. Resolve the PR first. |
| `feat/annotate-ui-redesign` | PR #8 was closed, not merged. Branch still shows commits not present on `main`. |
| `feat/parse-ai-connect-onboarding` | PR #19 merged into `feat/annotate-ui-redesign`, not into `main`. Branch still carries commits outside `main`. |

## Required follow-up before deleting the two unresolved feature branches

1. Review `feat/annotate-ui-redesign` and `feat/parse-ai-connect-onboarding` together.
2. Cherry-pick or re-land anything still wanted onto `feat/parseui-unified-shell`.
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
- Branches still carrying commits not on `main`:
  - `feat/annotate-ui-redesign`
  - `feat/parse-ai-connect-onboarding`

## Recommended execution order

1. Merge or close PR #7.
2. Salvage any still-needed commits from `feat/annotate-ui-redesign` and `feat/parse-ai-connect-onboarding`.
3. Delete the safe merged/superseded remote branches.
4. Run a separate local worktree cleanup pass.
