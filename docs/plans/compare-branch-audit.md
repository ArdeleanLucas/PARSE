# PARSE Phase 2 — `feat/compare-react` Branch Audit

**Purpose:** Decide whether `feat/compare-react` should be deleted, preserved, or intentionally revived.

**Captured on:** 2026-04-09  
**Active repo:** `/home/lucas/gh/ardeleanlucas/parse`  
**Audit branch:** `docs/phase2-compare-branch-audit`

---

## 1. Branches and refs audited

- `origin/main` → `737e0cf`
- `origin/feat/compare-react` → `b8ecd1e`
- local `feat/compare-react` worktree branch → `c726049`
  - attached worktree: `/home/lucas/gh/worktrees/parse/compare-react`
  - worktree status at audit time: clean, tracking `origin/feat/compare-react`, reported as `behind 17`

---

## 2. Raw git facts

### Remote branch vs `origin/main`

Command:

```bash
git rev-list --left-right --count origin/main...origin/feat/compare-react
```

Result:

- `origin/main` only commits: `10`
- `origin/feat/compare-react` only commits: `1`

Command:

```bash
git log --oneline origin/main..origin/feat/compare-react
```

Result:

- `b8ecd1e` — `merge: config+auth fixes (MC-281) into feat/compare-react`

Command:

```bash
git cherry -v origin/main origin/feat/compare-react
```

Result:

- no unmatched patch-equivalent commits

### Merge-base / tree analysis

Command:

```bash
git merge-base origin/main origin/feat/compare-react
```

Result:

- merge-base: `9adbbf494d7fe524e989f00501cdaddaa40396ff`

Command:

```bash
MB=$(git merge-base origin/main origin/feat/compare-react)
git diff --stat $MB..origin/feat/compare-react
```

Result:

- empty diff

Command:

```bash
MB=$(git merge-base origin/main origin/feat/compare-react)
git rev-parse $MB^{tree}
git rev-parse origin/feat/compare-react^{tree}
```

Result:

- merge-base tree: `2f36efdd231972c187504b830f311569e8175eab`
- compare branch tree: `2f36efdd231972c187504b830f311569e8175eab`

**Interpretation:** the remote branch's only unique commit is a merge commit whose final tree is identical to the merge-base tree. It contributes no surviving file-content delta beyond what is already represented in shared history.

### Local worktree branch vs `origin/main`

Command:

```bash
git rev-list --left-right --count origin/main...feat/compare-react
```

Result:

- `origin/main` only commits: `26`
- local `feat/compare-react` only commits: `0`

Command:

```bash
git log --oneline origin/main..feat/compare-react
```

Result:

- no local-only commits

**Interpretation:** the local worktree branch tip `c726049` is already fully subsumed by `origin/main` and contains no unpublished compare-only work.

---

## 3. Semantic reading

`feat/compare-react` was originally a real Compare-mode work lane during the React pivot. That historical role is legitimate, but it is no longer an active source-of-truth branch:

- the substantive Compare work from the branch is already reachable from `main`
- the remote branch's only remaining divergence is a stale merge commit (`b8ecd1e`)
- that merge commit is semantically empty at the tree level
- the attached local worktree branch is also stale and fully merged

So the branch still has **historical meaning**, but no remaining **technical necessity**.

---

## 4. Recommendation

## Delete the remote GitHub branch after Lucas approval

This is the recommended disposition for **`origin/feat/compare-react`**.

### Why deletion is justified

1. **No surviving code delta**
   - the only branch-only remote commit is tree-identical to the merge-base
   - `git cherry` finds no unmatched patch content

2. **All substantive compare work is already on `main`**
   - the local worktree branch has `0` commits not in `origin/main`

3. **The only thing not ancestry-merged is merge metadata**
   - branch tip `b8ecd1e` is not itself an ancestor of `origin/main`
   - deleting the remote branch drops that named merge commit reference, but not any unique surviving file content

4. **The branch name is now misleading**
   - it still sounds like the live compare lane even though the canonical path has moved through integration into `main`

5. **Reviving this branch would be worse than starting fresh**
   - if future Compare-only work is needed, create a new branch from current `main`
   - reviving this stale branch would reintroduce historical confusion

---

## 5. Local branch / worktree handling

### Recommended handling

- **Remote GitHub branch:** delete after Lucas approval
- **Local branch `feat/compare-react`:** can also be retired later, but only when Lucas is ready to remove the attached worktree
- **If the remote branch is deleted first:** the local worktree branch will keep working, but its upstream will become `gone` and should be unset or retargeted during cleanup
- **Do not revive the current branch name for new work**
  - if a new compare-focused lane is needed, cut a fresh branch from `main`

### Why keep local cleanup separate from remote cleanup

The local branch is attached to an existing worktree path:

- `/home/lucas/gh/worktrees/parse/compare-react`

That means local deletion should be done as part of a deliberate worktree cleanup pass, not as an incidental side effect of remote branch pruning.

---

## 6. Bottom line

`feat/compare-react` is **not** an active branch that needs preservation or revival.

It is best understood as **historical branch residue** from the React pivot.

**Decision:**
- remote branch: **delete after Lucas approval**
- local worktree branch: **retire later during worktree cleanup**
- future compare work: **start from fresh `main`, not from this branch**
