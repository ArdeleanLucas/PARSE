---
name: github-pr-workflow
description: Full pull request lifecycle — create branches, commit changes, open PRs, monitor CI status, auto-fix failures, and merge. Works with gh CLI or falls back to git + GitHub REST API via curl.
version: 1.3.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, CI/CD, Git, Automation, Merge]
    related_skills: [github-auth, github-code-review]
---

# GitHub Pull Request Workflow

Complete guide for managing the PR lifecycle. Each section shows the `gh` way first, then the `git` + `curl` fallback for machines without `gh`.

## Pitfalls

- **Local and remote have no common ancestor (fully diverged histories).** This happens when a remote was force-pushed to a "clean history" base (e.g. 2-commit squash) while the local branch still has the full development history. `git rebase origin/main` and `git push` both fail. `git merge-base origin/main HEAD` exits non-zero. `git log origin/main..HEAD` lists every local commit (i.e. the entire history, not just new work).

  **Diagnosis:**
  ```bash
  git fetch origin
  git merge-base origin/main HEAD  # exit 1 = no common ancestor
  git log --oneline origin/main -3  # see what remote actually has
  ```

  **Fix — temp-branch surgical patch (preferred):** Create a branch from `origin/main`, apply only your actual changes via `mcp_patch` or `git checkout <local-branch> -- file`, commit, push, then reset local `main`:
  ```bash
  git stash                              # stash any uncommitted changes
  git checkout -b temp-rebase origin/main
  # Apply changes via mcp_patch (surgical diffs) OR for files with no conflict:
  git checkout main -- python/some_file.py  # bring specific file from local main
  # For files that differ structurally, apply changes manually via patch tool
  git add <changed files>
  git commit -m "fix: ..."
  git push origin temp-rebase:main       # push to remote main
  git checkout main
  git reset --hard origin/main           # sync local main to remote
  git branch -d temp-rebase
  git stash pop                          # restore runtime data if needed
  ```

  **Why cherry-pick fails here:** If the remote is a restructured version of the codebase (same files, different layout), cherry-pick will produce conflicts everywhere because the line-level context doesn't match — even if the logical change is simple. Surgical `mcp_patch` on the remote's version of the file is cleaner.

  **PARSE context:** `TarahAssistant/parse_v2` was force-pushed to a clean 2-commit history. Local `main` had 140+ development commits on top of a different root. The surgical patch approach landed all fixes cleanly as a single commit `d9386a0`.

- **`--reviewer` fails if the reviewer isn't a repo collaborator.** `gh pr create --reviewer username` returns `could not request reviewer: 'username' not found` if the account lacks collaborator access on the repo. Omit `--reviewer` and let the repo owner assign review manually, or add them as a collaborator first.
- **Rebase before opening a PR when the branch has diverged from main.** If `git log origin/main..branch` shows commits but GitHub reports conflicts, do `git rebase origin/main` first. Resolve conflicts, then `git push --force-with-lease`. The PR will update automatically and show clean.
- **`git rebase --continue` needs an editor or `-m`.** In non-TTY environments (terminal tool), `git rebase --continue` fails with `Terminal is dumb, but EDITOR unset`. Use `GIT_EDITOR=true git rebase --continue` to accept the existing commit message.
- **`gh pr create --body "..."` and inline `gh pr comment --body "..."` strings can be shell-mangled when the text contains backticks or command-like markdown.** In Hermes/terminal contexts, markdown like `` `npm run test -- --run` `` or even plain commit/model references wrapped in backticks (for example `` `fdd9145` `` or `` `grok-4.20-0309-reasoning` ``) may be executed by the shell before `gh` sees them, producing `command not found` errors and silently posting damaged PR bodies/comments. In `gh 2.87.3`, both `gh pr create` and `gh pr comment` support `--body-file`, so make that the default safe path for any non-trivial markdown body/comment. If you accidentally post a mangled body/comment, immediately repair it with `gh pr edit <N> --body-file /tmp/pr-body.md` or `gh pr comment <N> --edit-last --body-file /tmp/pr-comment.md`.
- **If the target PR is already merged, do not reuse its branch as the submission target.** Verify PR state first (`gh pr view <N> --json state,mergedAt,headRefName,baseRefName`). If merged, branch from fresh `origin/main`, port only the still-relevant delta, and open a new follow-up PR from the correct active branch instead of pushing more work onto the merged PR branch.
- **Before closing a PR as stale/superseded, verify the successor lane and scope overlap — and close the PR, not the branch, unless deletion is explicitly requested.** Check the candidate PR's changed files and compare them with any newer open/merged PRs (`gh pr view`, `gh pr diff --name-only`). This prevents closing a still-unique PR by mistake and avoids deleting a branch the user may still want for reference. A good closeout comment should name the superseding PR(s), the scope mismatch or factual drift, and why a fresh follow-up from current `main` would be safer than merging the stale branch.
- **`gh pr create --project ...` needs the GitHub CLI `project` scope even when normal PR auth already works.** In `gh 2.87.3`, `gh pr create --help` explicitly warns that project assignment requires `gh auth refresh -s project`. If project attachment fails with a GraphQL/auth error, refresh that scope and retry.
- **`gh pr merge` may enqueue instead of merging immediately on repos with merge queue enabled.** In `gh 2.87.3`, `gh pr merge --help` states that if checks are still pending, auto-merge is enabled; if checks have already passed, the PR is added to the merge queue. Use `--admin` only when you intentionally mean to bypass queue/protection rules.

## Prerequisites

- Authenticated with GitHub (see `github-auth` skill)
- Inside a git repository with a GitHub remote

### Quick Auth Detection

```bash
# Determine which method to use throughout this workflow
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="git"
  # Ensure we have a token for API calls
  if [ -z "$GITHUB_TOKEN" ]; then
    if [ -f ~/.hermes/.env ] && grep -q "^GITHUB_TOKEN=" ~/.hermes/.env; then
      GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
    elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
      GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
    fi
  fi
fi
echo "Using: $AUTH"
```

### Extracting Owner/Repo from the Git Remote

Many `curl` commands need `owner/repo`. Extract it from the git remote:

```bash
# Works for both HTTPS and SSH remote URLs
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
echo "Owner: $OWNER, Repo: $REPO"
```

---

## 1. Branch Creation

This part is pure `git` — identical either way:

```bash
# Make sure you're up to date
git fetch origin
git checkout main && git pull origin main

# Create and switch to a new branch
git checkout -b feat/add-user-authentication
```

Branch naming conventions:
- `feat/description` — new features
- `fix/description` — bug fixes
- `refactor/description` — code restructuring
- `docs/description` — documentation
- `ci/description` — CI/CD changes

## 2. Making Commits

Use the agent's file tools (`write_file`, `patch`) to make changes, then commit:

```bash
# Stage specific files
git add src/auth.py src/models/user.py tests/test_auth.py

# Commit with a conventional commit message
git commit -m "feat: add JWT-based user authentication

- Add login/register endpoints
- Add User model with password hashing
- Add auth middleware for protected routes
- Add unit tests for auth flow"
```

Commit message format (Conventional Commits):
```
type(scope): short description

Longer explanation if needed. Wrap at 72 characters.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `perf`

## 3. Pushing and Creating a PR

### Push the Branch (same either way)

```bash
git push -u origin HEAD
```

### Create the PR

**With gh (recommended):**

Create `/tmp/pr-body.md` first — either from one of this skill's linked templates (`templates/pr-body-feature.md` or `templates/pr-body-bugfix.md`) or by writing your own markdown file — then pass it with `--body-file`:

```bash
gh pr create \
  --title "feat: add JWT-based user authentication" \
  --body-file /tmp/pr-body.md
```

Example `/tmp/pr-body.md` content:

```md
## Summary
- Adds login and register API endpoints
- JWT token generation and validation

## Test Plan
- [ ] Unit tests pass

Closes #42
```

Options: `--draft`, `--reviewer user1,user2`, `--label "enhancement"`, `--base develop`

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/$OWNER/$REPO/pulls \
  -d "{
    \"title\": \"feat: add JWT-based user authentication\",
    \"body\": \"## Summary\nAdds login and register API endpoints.\n\nCloses #42\",
    \"head\": \"$BRANCH\",
    \"base\": \"main\"
  }"
```

The response JSON includes the PR `number` — save it for later commands.

To create as a draft, add `"draft": true` to the JSON body.

## 4. Monitoring CI Status

### Check CI Status

**With gh:**

```bash
# One-shot check
gh pr checks

# Machine-readable status (note: exit code 8 means checks are still pending)
gh pr checks --json name,state,bucket,link

# Watch until all checks finish (polls every 10s)
gh pr checks --watch
```

**With git + curl:**

```bash
# Get the latest commit SHA on the current branch
SHA=$(git rev-parse HEAD)

# Query the combined status
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Overall: {data['state']}\")
for s in data.get('statuses', []):
    print(f\"  {s['context']}: {s['state']} - {s.get('description', '')}\")"

# Also check GitHub Actions check runs (separate endpoint)
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/check-runs \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cr in data.get('check_runs', []):
    print(f\"  {cr['name']}: {cr['status']} / {cr['conclusion'] or 'pending'}\")"
```

### Poll Until Complete (git + curl)

```bash
# Simple polling loop — check every 30 seconds, up to 10 minutes
SHA=$(git rev-parse HEAD)
for i in $(seq 1 20); do
  STATUS=$(curl -s \
    -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "Check $i: $STATUS"
  if [ "$STATUS" = "success" ] || [ "$STATUS" = "failure" ] || [ "$STATUS" = "error" ]; then
    break
  fi
  sleep 30
done
```

## 5. Auto-Fixing CI Failures

When CI fails, diagnose and fix. This loop works with either auth method.

### Step 1: Get Failure Details

**With gh:**

```bash
# List recent workflow runs on this branch
gh run list --branch $(git branch --show-current) --limit 5

# View failed logs
gh run view <RUN_ID> --log-failed
```

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

# List workflow runs on this branch
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/actions/runs?branch=$BRANCH&per_page=5" \
  | python3 -c "
import sys, json
runs = json.load(sys.stdin)['workflow_runs']
for r in runs:
    print(f\"Run {r['id']}: {r['name']} - {r['conclusion'] or r['status']}\")"

# Get failed job logs (download as zip, extract, read)
RUN_ID=<run_id>
curl -s -L \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/logs \
  -o /tmp/ci-logs.zip
cd /tmp && unzip -o ci-logs.zip -d ci-logs && cat ci-logs/*.txt
```

### Step 2: Fix and Push

After identifying the issue, use file tools (`patch`, `write_file`) to fix it:

```bash
git add <fixed_files>
git commit -m "fix: resolve CI failure in <check_name>"
git push
```

### Step 3: Verify

Re-check CI status using the commands from Section 4 above.

### Auto-Fix Loop Pattern

When asked to auto-fix CI, follow this loop:

1. Check CI status → identify failures
2. Read failure logs → understand the error
3. Use `read_file` + `patch`/`write_file` → fix the code
4. `git add . && git commit -m "fix: ..." && git push`
5. Wait for CI → re-check status
6. Repeat if still failing (up to 3 attempts, then ask the user)

## 6. Merging

**With gh:**

```bash
# Direct squash merge when branch protection allows it
gh pr merge --squash --delete-branch \
  --match-head-commit "$(git rev-parse HEAD)"

# Safe default for protected repos / merge queues
gh pr merge --auto --squash --delete-branch \
  --match-head-commit "$(git rev-parse HEAD)"
```

Notes:
- `--match-head-commit` prevents merging a stale head if new commits landed after you last verified the branch.
- On merge-queue repos, `--auto` typically enables auto-merge while checks are pending, then lets GitHub enqueue/merge when requirements are satisfied.

**With git + curl:**

```bash
PR_NUMBER=<number>

# Merge the PR via API (squash)
curl -s -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/merge \
  -d "{
    \"merge_method\": \"squash\",
    \"commit_title\": \"feat: add user authentication (#$PR_NUMBER)\"
  }"

# Delete the remote branch after merge
BRANCH=$(git branch --show-current)
git push origin --delete $BRANCH

# Switch back to main locally
git checkout main && git pull origin main
git branch -d $BRANCH
```

Merge methods: `"merge"` (merge commit), `"squash"`, `"rebase"`

### Enable Auto-Merge (curl)

```bash
# Auto-merge requires the repo to have it enabled in settings.
# This uses the GraphQL API since REST doesn't support auto-merge.
PR_NODE_ID=$(curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['node_id'])")

curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/graphql \
  -d "{\"query\": \"mutation { enablePullRequestAutoMerge(input: {pullRequestId: \\\"$PR_NODE_ID\\\", mergeMethod: SQUASH}) { clientMutationId } }\"}"
```

## 7. Complete Workflow Example

```bash
# 1. Start from clean main
git checkout main && git pull origin main

# 2. Branch
git checkout -b fix/login-redirect-bug

# 3. (Agent makes code changes with file tools)

# 4. Commit
git add src/auth/login.py tests/test_login.py
git commit -m "fix: correct redirect URL after login

Preserves the ?next= parameter instead of always redirecting to /dashboard."

# 5. Push
git push -u origin HEAD

# 6. Create PR (picks gh or curl based on what's available)
# ... (see Section 3)

# 7. Monitor CI (see Section 4)

# 8. Merge when green (see Section 6)
```

## Useful PR Commands Reference

| Action | gh | git + curl |
|--------|-----|-----------|
| List my PRs | `gh pr list --author @me` | `curl -s -H "Authorization: token $GITHUB_TOKEN" "https://api.github.com/repos/$OWNER/$REPO/pulls?state=open"` |
| View PR diff | `gh pr diff` | `git diff main...HEAD` (local) or `curl -H "Accept: application/vnd.github.diff" ...` |
| Add comment | `gh pr comment N --body-file /tmp/pr-comment.md` | `curl -X POST .../issues/N/comments -d '{"body":"..."}'` |
| Request review | `gh pr edit N --add-reviewer user` | `curl -X POST .../pulls/N/requested_reviewers -d '{"reviewers":["user"]}'` |
| Close PR | `gh pr close N` | `curl -X PATCH .../pulls/N -d '{"state":"closed"}'` |
| Check out someone's PR | `gh pr checkout N` | `git fetch origin pull/N/head:pr-N && git checkout pr-N` |
