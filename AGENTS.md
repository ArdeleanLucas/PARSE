# AGENTS.md — PARSE React + Vite Integration (2026)

## Post-cutover banner (added 2026-04-27)

This repository — `ArdeleanLucas/PARSE` — became the canonical PARSE on 2026-04-27 via:

1. Old `ArdeleanLucas/PARSE` renamed to `ArdeleanLucas/PARSE-pre-rebuild-archive` and archived
2. `TarahAssistant/PARSE-rebuild` transferred to ArdeleanLucas, renamed to `PARSE`
3. `TarahAssistant/PARSE-rebuild-archive` retained as private historical mirror

**Going forward:** "the rebuild" and "the oracle" terminology is obsolete. Just call it PARSE. Sign-off doc at `parity/harness/SIGNOFF.md` records the audit that gated cutover (raw harness diff = 0).

The repo-target rule below is updated post-cutover: PRs land on `ArdeleanLucas/PARSE`, NOT on the archived repos.

> **Post-cutover clone note (2026-04-29):** the physical checkout path `/home/lucas/gh/tarahassistant/PARSE-rebuild` is historical, but its `origin` is the canonical `git@github.com:ArdeleanLucas/PARSE.git`. Use PARSE terminology for current work; use "rebuild/oracle" only when discussing archived pre-cutover evidence.

## Repo-target rule (READ BEFORE OPENING ANY PR)

All work lands on **`ArdeleanLucas/PARSE`** (the canonical post-cutover repo). The pre-cutover archives — `ArdeleanLucas/PARSE-pre-rebuild-archive` (read-only) and `TarahAssistant/PARSE-rebuild-archive` (private historical mirror) — should never receive new work. Three prior refactor PRs landed on what was then the wrong remote and had to be reverted or replayed:

- `ArdeleanLucas/PARSE#225` — reverted in oracle commit `0951287` (`revert: move refactor PRs out of live PARSE (#228)`)
- `ArdeleanLucas/PARSE#226` — reverted in the same commit
- `ArdeleanLucas/PARSE#229` — closed without merging on 2026-04-26; replayed onto rebuild as `TarahAssistant/PARSE-rebuild#68`

Before opening any PR for any task in this lane, verify all three:

1. **Working clone** is the canonical PARSE clone:
   ```
   $ pwd
   /home/lucas/gh/tarahassistant/PARSE-rebuild   # CORRECT (post-cutover, this directory's `origin` now resolves to ArdeleanLucas/PARSE; directory name preserved to avoid breaking worktrees)
   ```
   NOT `/home/lucas/gh/ArdeleanLucas/PARSE` (oracle clone, capital).
   NOT `/home/lucas/gh/ardeleanlucas/parse` (oracle clone, lowercase duplicate).
   NOT any worktree under `/home/lucas/gh/worktrees/PARSE/...` whose `.git` gitfile resolves to either oracle clone above. Worktrees inherit the parent clone's remote.

2. **Origin remote** points at canonical PARSE, not an archive:
   ```
   $ git remote -v
   origin\tgit@github.com:ArdeleanLucas/PARSE.git (fetch)   # CORRECT
   origin\tgit@github.com:ArdeleanLucas/PARSE.git (push)
   ```
   If the URL says `ArdeleanLucas/PARSE`, you are on the correct canonical remote. If it points to `PARSE-pre-rebuild-archive`, `TarahAssistant/PARSE-rebuild-archive`, or another archive/fork, **stop** and switch to `/home/lucas/gh/tarahassistant/PARSE-rebuild` (or a worktree created from it) before doing anything else.

3. **PR-create command** explicitly targets the canonical repo:
   ```
   $ gh pr create --repo ArdeleanLucas/PARSE --base main ...
   ```
   The `--repo` flag is **mandatory**. Without it, `gh` infers the remote from the local clone's origin, and any agent in a stale archive clone or worktree may target the wrong repo. **Do not omit the `--repo` flag.**

If you ever see a PR URL targeting `ArdeleanLucas/PARSE-pre-rebuild-archive` or `TarahAssistant/PARSE-rebuild-archive`, **close it immediately** and replay the commit onto `ArdeleanLucas/PARSE` via `git cherry-pick`. The recovery path is documented in `docs/plans/2026-04-26-parse-back-end-next-chat-tools-decomposition.md` §Recovery path.

Exceptions to this rule (cases where landing on oracle IS correct):

- A live thesis-runtime bug fix that Lucas explicitly requests — open the PR on `ArdeleanLucas/PARSE` with title prefix `fix(live):`
- A controlled sync/revert PR moving a previously-merged change between repos — open on whichever repo is the target, with title prefix `sync(oracle->rebuild):` or `revert(oracle):`

Both exceptions require Lucas's explicit approval per task. Do not assume.

## Scope: Desktop (Option 3) REVIVED 2026-07-04 — supersedes the 2026-04-26 cancellation

Per Lucas decision **2026-07-04**, the desktop/installable product direction (**Option 3**) is **revived**, explicitly reversing the 2026-04-26 cancellation (recorded below for history). Goal: PARSE ships as a **downloadable, installable desktop app** — macOS first, then Windows — using the Electron shell + local Python backend architecture in `docs/desktop_product_architecture.md`.

Practical implications:

- Desktop work is back in scope. The `desktop/` Electron scaffold is the starting point — extend it, don't restart it.
- **First**, lift the CANCELLED/ARCHIVED banners on `docs/desktop_product_architecture.md`, `desktop/README.md`, and `docs/archive/plans/option1-separate-rebuild-to-option3-desktop-platform.md`, and refresh the plan + `docs/distribution_readiness_checklist.md` against the current codebase (several old blockers are resolved; new ones — `/api/project` write contract, offset/spectrogram compute routes, `0.0.0.0`/CORS defaults, no dependency lock / managed Python runtime — are not).
- **Option 1 (web/React) remains the foundation and stays working throughout.** Desktop packaging wraps the existing React SPA + Python backend; it does not replace them. Parity evidence still covers React shell + Python backend + on-disk artifacts.
- Release gates follow `docs/distribution_readiness_checklist.md` (Gate A → B → C). "Downloadable and installable" means clearing at least Gate B (installers + managed Python runtime), ideally Gate C (signing/notarization).

Reversal rule retained: any future change to this direction must be recorded **here, explicitly, with a dated decision** — no implicit changes in either direction.

> **Superseded (historical) — Option 1 only, 2026-04-26:** the rebuild's done-state was Option 1 complete and Option 3 (desktop) was dropped; no desktop work, no electron/tauri scaffolding, `desktop_product_architecture.md` archived. Reversed 2026-07-04 per the rule above.

### AIChat.tsx is maintenance-mode-only (added 2026-04-26)

Per Lucas decision 2026-04-26: the in-app AI chat panel (`src/components/shared/AIChat.tsx`) is **maintenance-mode-only**. No new chat UI features should ship. The component stays mounted and functional but does not receive product investment.

**What's still in scope:**

- `python/ai/chat_tools.py` (registry/orchestrator; concrete tool modules live under `python/ai/tools/` and `python/ai/chat_tools/`) decomposition (PRs 2/3/4 — foundation for internal programmatic tool use AND MCP exposure, not chat-UI-specific)
- `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) decomposition (env_config.py PR 1 + follow-ups)
- The 58 chat tools themselves (they're the internal tool surface; PARSE uses them programmatically beyond just the chat UI)
- Bug fixes that touch AIChat.tsx incidentally (e.g., the path-separator fix at PR #77 affected stt_start which AIChat consumes)

**What's dropped:**

- New AIChat features (Quick Actions additions, provider switch UX improvements, message history features, etc.)
- AIChat parity evidence pass (was queued as inventory §12 priority position 2; now removed entirely from the priority list)
- AIChat-specific test coverage gaps (don't add new tests for chat-only behavior)
- Any chat-side performance / latency optimization work

**Practical guidance:**

- If a chat_tools.py decomposition PR incidentally touches AIChat.tsx (e.g., to update an import path), that's fine — keep the change minimal.
- If a parity evidence pass against another P0/P1 surface reveals a chat-related bug, file an issue and triage; do NOT add it to active work.
- Re-adding AIChat features later is cheap because the component is fully extracted (PR #61) and the tools are decomposed. ~1 day of work to re-enable a feature lane if Lucas reverses this decision.

## Refetch before reporting PR status (added 2026-04-26)

**Always run `git fetch origin --quiet --prune` immediately before reporting any PR's mergeable/conflict status to coordinator or Lucas.**

Failure mode observed multiple times tonight: agent reports a PR as `MERGEABLE/CLEAN` based on the local clone's stale state, but `gh pr view <N> --json mergeable,mergeStateStatus` against current GitHub state returns `CONFLICTING/DIRTY` because main has moved since the agent last fetched.

**Why it happens:** `gh pr view` reads the most recent state GitHub has computed. GitHub's mergeable computation runs whenever main changes. If your local clone hasn't fetched the latest origin/main, your mental model of the PR's state is stale even though `gh` returns fresh data — you're comparing your branch against an old base in your head.

**Concrete check before any status report:**

```
$ git fetch origin --quiet --prune
$ gh pr view <N> --repo ArdeleanLucas/PARSE --json mergeable,mergeStateStatus,baseRefOid,headRefOid
```

Report what `gh` returned, not what you remember from earlier. If the result surprises you (e.g., you just rebased and now it says CONFLICTING), check whether main moved between your rebase and this query.

**Why this matters for the merge tail:** the merge wave tonight processed ~30 PRs in ~3 hours. Branches created during the wave go stale within minutes. Coordinator (parse-coordinator) and Lucas need accurate mergeable status to decide what to merge next. False-positive CLEAN reports cause Lucas to attempt merges that fail, then chase phantom rebase requests.

**Applies to:**

- Implementation lanes (parse-front-end, parse-back-end) reporting their own PR status after shipping
- Coordinator (parse-coordinator) reporting on PRs queued for merge
- Any handoff or task-log entry that includes a PR mergeable claim

Skip the refetch only if you are ABSOLUTELY certain main hasn't moved since your last fetch in the same session. If in doubt, refetch — it's a 1-second operation.

## PR base discipline (post-cutover)

Every `gh pr create` MUST pass `--base main` explicitly. After creation, the agent MUST verify with `gh pr view <N> --repo ArdeleanLucas/PARSE --json baseRefName` returning `"baseRefName":"main"` BEFORE announcing the PR. If the base is anything else (a feature branch, a stale fix branch, a docs branch from another PR, etc.), abort and either retarget via `gh pr edit <N> --base main` or close + reopen with the correct base.

```bash
$ gh pr create --repo ArdeleanLucas/PARSE --base main \
    --title "..." --body "..."
https://github.com/ArdeleanLucas/PARSE/pull/N

$ gh pr view N --repo ArdeleanLucas/PARSE --json baseRefName
{"baseRefName":"main"}        # <-- must say exactly "main"; abort if not
```

**Failure mode this prevents:** 2026-05-01 — PR #234 was opened with `base: fix/annotate-arrow-key-concept-nav` (PR #231's branch) instead of `base: main`. The handoff said to *branch off* that branch so the work would stack regardless of merge order. The agent did that for the source branch but ALSO inferred the PR base from the source branch instead of explicitly setting it to main. When merged, commit 67976a0c landed in the obsolete side branch only — `main` was never updated, and the bug the PR was supposed to fix stayed in production. Lucas had to cherry-pick the fix into a fresh branch off main and ship it as PR #235.

**The two decisions are independent.** Stacking source branches off feature branches is a legitimate technique when an upstream PR is in flight (it lets your work apply cleanly regardless of merge order). Setting PR bases off feature branches is NOT — the PR base controls where the merge lands, period. Always pass `--base main` even when the source branch is stacked elsewhere.

**When in doubt, base = main. Always.**

**Labels mandatory on every `gh pr create`:** include the MC parent label (for example `--label MC-384`) plus at least one type label (`docs`, `bugfix`, `feat`, `test`, `chore`, etc.) directly on `gh pr create`; verify before announcing with `gh pr view <N> --repo ArdeleanLucas/PARSE --json labels`. Regression: PR #421 shipped with `labels: []`, breaking MC-parent filtering.

## Agent identities and parallel worktrees (added 2026-04-27)

The three implementation lanes are:

| Identity | Domain | Owns |
|---|---|---|
| `parse-back-end` | All `python/` | `python/server_routes/`, `python/ai/`, `python/adapters/`, `python/packages/parse_mcp` |
| `parse-front-end` | All `src/` | `src/components/`, `src/stores/`, `src/hooks/`, `src/api/contracts/` |
| `parse-coordinator` | `parity/`, `.hermes/`, `docs/` | parity harness, handoff PRs, scorecards, sign-off audits, dogfood reports, integration audits |

**Renamed 2026-04-27:** `parse-builder` → `parse-front-end`, `parse-gpt` → `parse-coordinator`. The old identifiers remain valid aliases during migration; new prompts and handoff docs use the new names. Existing handoff doc paths under `.hermes/handoffs/parse-builder/` and `.hermes/handoffs/parse-gpt/` are preserved as historical record — do not rename retroactively.

### Parallel work via worktrees

The post-decomp module layout enables a single agent identity to run multiple in-flight PRs concurrently by maintaining git worktrees, one per active branch. Each worktree shares the canonical clone's git object store but has an isolated working tree, so two streams from the same agent never collide on filesystem state.

**Convention:**

- Canonical clone (long-lived, kept at `origin/main`): `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- Active worktrees (per-branch, ephemeral): `/home/lucas/gh/worktrees/<agent>-<slug>/`

The slug is a 2-4 word kebab-case description of the work (e.g. `back-end-mcp-tool-coverage`, `front-end-clef-port`, `coordinator-harness-round3`).

**Recipe — start a new parallel stream:**

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --quiet --prune
git worktree add -f /home/lucas/gh/worktrees/<agent>-<slug> origin/main
  # parent clone's origin must already point at git@github.com:ArdeleanLucas/PARSE.git
cd /home/lucas/gh/worktrees/<agent>-<slug>
git checkout -b <branch-name>
# do the work, commit, push, open PR with --repo ArdeleanLucas/PARSE
```

**Hard rule — never branch in the canonical clone:**

The canonical clone at `/home/lucas/gh/tarahassistant/PARSE-rebuild` MUST stay on `main` at all times. It is what `parse-run` boots Vite from on Lucas's PC; if it sits on any other branch, the dev server warns ("canonical clone is on '...', not main. Frontend may be stale.") and may serve stale UI. Therefore:

- DO NOT run `git checkout -b <branch>` inside the canonical clone for any reason. Always `git worktree add` first, then `git checkout -b` inside the worktree.
- DO NOT amend, rebase, or commit inside the canonical clone. The canonical clone only fast-forwards `origin/main`.
- Even tiny docs-only PRs go through a worktree. There is no "small enough to skip" escape hatch.

**Recipe — clean up after PR merges:**

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --quiet --prune
# Verify canonical clone is on main; if it drifted, restore it.
current_branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$current_branch" != "main" ]; then
  git checkout main
  git pull --ff-only origin main
  git branch -D "$current_branch" 2>/dev/null || true
fi
git worktree remove -f /home/lucas/gh/worktrees/<agent>-<slug>
git branch -D <branch-name> 2>/dev/null || true
# Verify clean state:
git status --short --branch  # should print: ## main...origin/main
```

GitHub auto-cleans the remote branch on merge; remove both the local worktree and its local feature branch before declaring the handoff complete.

**Constraints:**

- Every worktree inherits the parent clone's `origin` remote — re-verify `git remote -v` shows `ArdeleanLucas/PARSE` before any PR (per repo-target rule above). Worktrees from a stale archive clone will silently push to the wrong repo.
- Each worktree needs its own `npm install` if running tests or builds — `node_modules/` is per-worktree, not shared.
- Each worktree needs distinct ports if booting the live backend — `parse-rebuild-run` already uses 8866/5174 to coexist with oracle on 8766/5173. Multiple rebuild backends would need additional port shifts.
- Cap per agent: 2-3 concurrent worktrees. More than that and the agent loses thread; queue subsequent tasks instead of fanning out further.

### Coordinator role (post-rename clarification)

`parse-coordinator` (formerly `parse-gpt`) explicitly owns:

- **Parity harness** — `parity/harness/` infrastructure, fixture maintenance, allowlist tightening, coverage extension
- **Sign-off audits** — `python -m parity.harness.runner --emit-signoff`, filling `parity/harness/SIGNOFF.md`, shipping superseding scorecards
- **Dogfood reports** — end-to-end UI dogfood passes against fixture data, filing GitHub issues for findings
- **Process coordination** — handoff PRs, scorecard refreshes, merge-tail draining, PR queue prioritization
- **Cross-cutting integration audits** — when a feature or bug spans multiple agents' domains, the coordinator owns the integration story

`parse-coordinator` is NOT an implementation lane — it does not own monolith decompositions or large feature work. If a coordinator audit surfaces a real bug, the fix is queued to `parse-back-end` or `parse-front-end`, not done in-line by the coordinator.

## Port-PR audit rule (added 2026-04-27)

When `parse-coordinator` reviews a `port: oracle #N` PR, the agent's claim that "the feature was already present" or "this PR adds regression-proof coverage" must be verified by grep before merge — not trusted on its own.

**Failure mode that motivated this rule:** PR #146 (`port: lock oracle frontend batch on rebuild parity surfaces`) claimed all 5 oracle PRs in its batch (#221, #218, #224, #222, #217) were already in rebuild main and shipped only regression tests. Partially true — Words+Boundaries lanes WERE present from earlier work — but partially false: the orphaned backend batch (#214, #216, #219) was assumed already-present and silently dropped on the floor for ~24h until coordinator re-audit caught the gap. By that point, oracle had shipped 5 more PRs (#238–#242) the rebuild also lacked.

**Required check before merging any `port: oracle #N` PR:**

1. Identify each oracle PR in the port batch by distinguishing strings — function names, identifiers, comments, UI button labels, MCP tool names. Pull them from `gh pr diff <N> --repo ArdeleanLucas/PARSE`.

2. Grep current rebuild main for each string:

   ```bash
   cd /home/lucas/gh/tarahassistant/PARSE-rebuild
   git fetch origin --quiet --prune
   git checkout origin/main --quiet
   grep -rE "<distinguishing-string>" src/ python/
   ```

3. **If the string is absent on main:** the port wasn't applied. Cross-check the port PR's diff — if the diff adds the matching code, port is real → safe to merge. If the diff lacks the matching code, port is **misclassified** → block merge. Comment on the PR explaining what's missing.

4. **If the string is present on main:** the port either landed earlier or the agent correctly identified pre-existing coverage. Either way: safe to merge.

**Why grep, not test count:** tests can pass against any state (even one that lacks the new feature) if the test fixtures don't exercise the new behavior. The Parity Diff Harness against the Saha 2-speaker fixture has shown 0 diff while the rebuild was missing several oracle features that simply aren't exercised by the fixture. Grep on identifier strings is the only cheap signal that the feature code itself is present.

**Examples of distinguishing strings to derive per oracle PR:**

| Change type | String to grep |
|---|---|
| New MCP tool | tool's registered name (e.g. `compute_boundaries`, `bnd_stt`) |
| New UI button | button's label (e.g. `"Phonetic Tools"`) |
| New lane / panel | component name (e.g. `BoundariesLane`, `WordsLane`) |
| Backend fix | changed function name + a snippet of new logic |
| New API endpoint | route path (e.g. `/api/compute/boundaries`) |
| New tier | tier identifier (e.g. `tiers.ortho_words`, `bnd_tier`) |

**Coordinator workflow on every `port:` PR:**

1. List the oracle PRs the port claims to cover (from PR description's "Oracle mapping" section or commit log).
2. For each oracle PR, derive 1-2 distinguishing strings via `gh pr diff <oracle-N> --repo ArdeleanLucas/PARSE`.
3. Grep current rebuild main; record present/absent for each string.
4. Cross-check against the port PR's diff to determine: real port (diff adds the missing feature), pre-existing (string already on main), or misclassified (absent and not added).
5. Document the audit as a PR review comment so future coordinators inherit the trail.

This rule applies specifically to `port: oracle #N` PRs. It does not apply to feature PRs (where the agent is writing new code from scratch) or refactor PRs (where parity harness is the gate).

## PR review rules — language, readability & docs (added 2026-06-01)

Every PR review must check these, and **apply the fixes during the review — do not ask first, and do not merely list them as suggestions.** This is the repo-side codification of Section 8 of the mandatory PR review checklist.

1. **Language/data-agnostic text.** The PR title, description, and review comments describe the *generic mechanism first* — the behavior, code path, or invariant — not one natural language, speaker, or corpus. Real data may appear only as a demoted example (e.g. "...the Persian/Farsi reference row, as one case"); the text must still read as general if the example were removed. Rewrite dataset-bound framing ("fixes the Kurdish hair concept") into the mechanism it changes ("fixes per-speaker flag state for any concept; hair was the observed case").
2. **Human-readable language.** Plain, simple, clear prose. Short sentences, lead with what changed and why. No filler or jargon stacks. A non-author engineer should understand the PR from the description alone.
3. **Docs assessment.** State explicitly whether the change warrants docs: *present* / *missing-but-warranted* / *not needed*. Any docs touched by the diff (README, `docs/`, in-repo guides, doc comments) must also satisfy rules 1 and 2. If docs are missing but warranted and the addition is small, add them in the PR.

When the PR body or a comment violates rule 1 or 2, edit it in the same pass: `gh pr edit <N> --repo <repo> --body "<rewritten>"` for the description, an edited/follow-up comment for review text, and direct file edits for docs in the diff. Record what was changed in the review's final verdict.

## Standard validation commands (added 2026-04-27)

Use these exact invocations in PR validation. Paraphrasing breaks in subtle ways — the wrong wrapper can wedge in fresh worktree configs.

| Purpose | Command |
|---|---|
| Frontend tests (one-shot) | `npx vitest run` |
| Frontend tests (specific file) | `npx vitest run path/to/file.test.ts` |
| Frontend tests (watch) | `npx vitest` |
| TypeScript check | `./node_modules/.bin/tsc --noEmit` |
| Frontend build | `npm run build` |
| Backend tests (full) | `PYTHONPATH=python python3 -m pytest python/ -q` |
| Backend tests (targeted) | `PYTHONPATH=python python3 -m pytest python/path/to/test_*.py -q` |
| Backend lint (pre-push, parse-back-end mandatory) | `uvx ruff check python/ --select E9,F63,F7,F82` |
| Server boot smoke (script mode) | `python python/server.py` — must bind without NameError post-PR #139 |
| Parity harness | `PYTHONPATH=. python -m parity.harness.runner --oracle ../ardeleanlucas/parse --rebuild . --fixture saha-2speaker` |

### Avoid these patterns

- **`npm run test -- --run`** — the `npm run test` script is already `"vitest run"`, so this double-passes `--run` and wedges in some fresh-worktree configs. Use `npx vitest run` instead. Found via parse-front-end PR #149 ship report (2026-04-27).
- **`pytest python/`** without `PYTHONPATH=python` — modules under `python/` won't resolve their internal imports.
- **`python server.py`** from a workspace under `/mnt/` — server.py refuses Windows-mount workspaces (FATAL guard, by design — WSL ext4 only).
- **Running test commands from the canonical clone while a worktree has uncommitted changes** — vitest may pick up the wrong working tree state. Run validation in the worktree where the changes live.

### Why these commands are codified here

Drift between agent prompts ("npm run test", "pytest python/", "uvx ruff", etc.) caused intermittent CI surprises (PR #133 ruff F821, parse-front-end PR #149 vitest wedge). Standardizing to one canonical invocation per purpose eliminates that class of problem.

Update this table when:
- A test framework version change shifts the invocation
- A new validation gate is added (e.g., a new ruff rule subset)
- A worktree-specific pitfall surfaces

## Screenshot convention (private-repo constraint)

**Use markdown links, NOT inline image embeds, for screenshots in PR descriptions.** This repo is private; inline `<img>` fetches in PR bodies do not carry repo auth, so `raw.githubusercontent.com` and `github.com/.../blob/...?raw=1` URLs 404 silently for everyone — including the PR author.

**Working pattern:**

```markdown
## Screenshot

[Screenshot: AnnotateView post-extraction](docs/pr-assets/foo.png)
```

**Failing patterns to avoid:**

```markdown
![alt](https://raw.githubusercontent.com/ArdeleanLucas/PARSE/<branch>/docs/pr-assets/foo.png)
![alt](https://github.com/ArdeleanLucas/PARSE/blob/<branch>/docs/pr-assets/foo.png?raw=1)
```

Both 404 in browsers. Verified 2026-04-26 — every screenshot embed in PRs #62, #63, #73, #79, #86 was failing silently. The screenshot rule had been doing nothing.

Why the link works: clicking the markdown link navigates to GitHub's blob view, which respects the viewer's auth session. Reviewers see the image one click away. Agents can do this trivially with no API changes.

**File location convention** unchanged: commit screenshots as binary files under `docs/pr-assets/<pr-number-or-slug>-<descriptor>.png`.

**Sanity-check your screenshot is real**: capture distinct browser states for each PR. If your screenshot tool keeps producing byte-identical PNGs across different PRs (compare blob SHAs), the tool is capturing a blank/error state, not real UI. Investigate before adding more screenshot evidence.

## Current code-layout guardrails (post-decomp)

When the docs or older plans mention the historical monoliths, translate them through the current split layout:

- `python/server.py` — thin HTTP orchestrator; concrete route domains live under `python/server_routes/`
- `python/ai/chat_tools.py` — registry/orchestrator; concrete tool logic lives under `python/ai/tools/` and `python/ai/chat_tools/`
- `python/adapters/mcp_adapter.py` — thin stdio MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`
- `python/ai/provider.py` — base-provider surface only; concrete providers live under `python/ai/providers/`
- `src/api/client.ts` — barrel only; concrete helpers live under `src/api/contracts/`
- `src/stores/annotationStore.ts` — barrel only; concrete annotation-store helpers live under `src/stores/annotation/`
- compare/annotate/CLEF top-level `.tsx` files may now be barrels; check `docs/architecture/post-decomp-file-map.md` before adding new logic directly into an old top-level entrypoint

## Current State (updated 2026-05-07)

PARSE has crossed the React pivot and the unified UI redesign is **merged to `main`**.

- **UI Redesign landed** (MC-294, merged via multiple PRs through PR #31):
  - `src/ParseUI.tsx` — unified shell (Annotate + Compare + Tags + AI Chat in one layout)
  - `App.tsx` simplified to `<BrowserRouter><ParseUI /></BrowserRouter>`
  - Dependencies: `lucide-react`, `tailwindcss v3`, `postcss`, `autoprefixer`
  - Wired: `useWaveSurfer`, `useChatSession`, `useConfigStore`, `useTagStore`, `usePlaybackStore`, `useUIStore`, `useAnnotationSync`
  - Spectrogram Worker TS port + `useSpectrogram` hook (MC-297, PR #31)
  - Annotate prefill/save/mark/badge, compare real data, import modal, notes, compute basics, decisions basics, tags bulk-selection — all landed
- **Cross-mode integration landed on current `main`**:
  - Track merge (`feat/annotate-react` + `feat/compare-react`) completed
  - Cross-mode navigation (Annotate ↔ Compare)
  - Store persistence regression coverage
  - API regression suite + CLEF integration coverage
- **CLEF shipped and hardened**:
  - Provider registry in `python/compare/providers/` with provenance-aware source reporting, provider warnings, exact doculect matching, guided Configure CLEF UX, Settings-tab reset controls, and Wiktionary translation-table extraction
  - Compare UI panel in `src/components/compare/ContactLexemePanel.tsx`
  - Server endpoints:
    - `POST /api/compute/contact-lexemes`
    - `GET /api/contact-lexemes/coverage`
    - `GET /api/clef/config`, `POST /api/clef/config`, `GET /api/clef/catalog`, `GET /api/clef/providers`, `GET /api/clef/sources-report`
    - `POST /api/clef/form-selections`
    - `POST /api/clef/clear` (dry-run-capable reference-form/cache clear; also exposed as MCP/chat tool `clef_clear_data`)
  - 2026-04-29 CLEF fixes: sources UX (#168), real tab targeting (#171), exact doculect matching (#174), clear endpoint/tool (#175), warning surfacing (#176), xAI/Grok auth alignment (#177), and `grok_llm` rename + Wiktionary translation tables + Settings tab (#182)
- **Annotate lexeme save/retime hardened**:
  - PR #172 bundled Save Annotation across concept/IPA/ORTH/`ortho_words` scope.
  - PR #179 changed save/drag retiming to use best-overlap matching for IPA/ORTH and midpoint rescaling for `ortho_words` so the derived BND lane follows lexeme bounds.
  - PR #180 creates a missing IPA interval on Save Annotation when the concept span matches and the typed IPA has no overlapping IPA interval.
  - PR #188 refreshes saved lexeme bounds in local edit state; PR #195 unwraps the full server-normalized annotation response and reports distinct changed tier names from server state.
  - PR #204 preserves Audition trace fields (`concept_id`, `import_index`, `audition_prefix`, `source`, `conceptId`) through annotation save/read normalization.
  - PRs #205/#208 make frontend concept lookup identity-only: `concept_id` equality is the only match path; interval text is display metadata and legacy concept rows without `concept_id` fail loudly as unannotated.
  - PR #207 adds the backend save-time gate that resolves non-empty concept-tier labels to integer `concept_id` values against `concepts.csv`, allocating new integer ids for unknown labels before writing annotations.
  - Save Annotation and quick-retime success copy now derive from server-normalized tier changes (`concept`, `ipa`, `ortho`, `ortho_words`) so BND/Words visual state follows saved bounds.
- **Concept-scoped pipeline reruns shipped**:
  - PR #190 and PR #193 lock/repair the `run_mode`, `concept_ids`, and `affected_concepts` contract.
  - PR #191 adds frontend full / concept-windows / edited-only controls in `TranscriptionRunModal`, edited-concepts preview, scoped step gating, and `applyConceptScopedRefresh`.
  - PR #192 ships backend/MCP/`parse_mcp` support for `run_mode` (`full`, `concept-windows`, `edited-only`) and optional `concept_ids` across STT, ORTH, IPA, and `run_full_annotation_pipeline`.
  - PR #196 removes English concept/gloss `initial_prompt` seeding from concept-window short clips and resolves transcription language from payload, then `annotation.metadata.language_code`, with a warning before Whisper auto-detect.
  - PR #212 makes full-mode IPA auto-route to concept-window processing when `ortho`/`ortho_words` are empty but concept intervals exist, preserving the legacy early return only when concept intervals are absent.
  - PR #215 makes post-compute disk reload canonical: `affected_concepts` / scoped row refresh is an advisory optimization, and `reloadSpeakerAnnotation` must still run after IPA, ORTH, STT, or BND compute completion so disk-written intervals appear in the UI.
  - PR #217 makes the Run Full Pipeline preview run-mode-aware for IPA: in `concept-windows` / `edited-only`, stale full-mode `ipa.can_run=false` no longer blocks the cell when ORTH/concept-tier presence is observable; full-mode IPA-without-ORTH and pure-empty concept-window speakers remain blocked.
  - PRs #221/#224/#225 add cancellation across the batch/UI/backend boundary: Cancel stops frontend polling immediately, fire-and-forget posts `POST /api/compute/{jobId}/cancel`, and HF ORTH cooperatively exits with `status: partial_cancelled` / `cancelled_at_interval` when work already produced intervals.
  - PRs #289/#290/#293 add synchronous reviewer-triggered `POST /api/lexeme/run_ortho` and `POST /api/lexeme/run_ipa` endpoints plus React confirm flows; requests accept `speaker`, `concept_key`, `start`, `end`, and `pad` (`0.0`, `0.2`, `0.5`), return the original interval bounds, and auto-persist confirmed ORTH/IPA text through the existing annotation save path.
  - PRs #298/#301/#302/#304 thread the same pad vocabulary through lexeme rerun dialogs and STT/ORTH/IPA action-menu concept-window / edited-only compute payloads; pad widens acoustic context without retiming reviewed intervals.
- **Annotate review UX polished**:
  - PRs #184/#185 add waveform drag-selection quick retime, a two-decimal waveform playhead chip, and cancel/Escape for transient retime selections.
  - PRs #186/#187 add manual volume control with default 100%.
  - PR #194 adds per-lexeme speaker notes, the generic `Orthographic` label, visible-list keyboard navigation, and removes the compute drawer tag filter.
  - PR #197 removes duplicate Annotate drawer concept filters; `ConceptSidebar` remains the canonical concept filter.
  - PRs #209/#211 split header status into strict `Annotated` vs `Complete` badges: `Complete` requires concept + IPA + strict `ortho` overlap, and auto-imported `ortho_words` no longer count as human-reviewed orthography.
  - PR #210 moves BND progress into the existing global header chip instead of duplicating progress text inside the drawer.
  - PR #223 makes the ORTHOGRAPHIC editor prefer direct `tiers.ortho` text before falling back to imported/derived `ortho_words`, preserving existing save flow into `tiers.ortho`.
  - PRs #275/#279/#287/#288 add lexeme-search tier filtering, graceful display for concept intervals past source-audio end, durable Annotate speaker-note edits, and Mark Done flushing of pending inline edits before confirmation.
  - PRs #284/#294 scope tag filters/counts and sidebar concept visibility by active speaker so Annotate does not surface another speaker's unelicited concepts or tag state.
  - PR #286 keeps annotation matching on the raw concept key rather than display ids, preserving source identity through source-item and duplicate/variant workflows.
- **Speaker onboarding from Audition CSV shipped**:
  - PR #198 teaches `POST /api/onboard/speaker` to detect Adobe Audition marker CSVs when concepts-style parsing finds no rows and `Name`/`Start` headers are present.
  - PR #200 resolves Audition labels against existing `concepts.csv` `concept_en` values before allocating new integer ids, so the import path remains integer-id only while preserving duplicate/repeated elicitations as separate intervals.
  - PR #201 adds companion comments CSV support via multipart `commentsCsv`; matching cue/comment rows are joined by zero-based row index into `parse-enrichments.json` lexeme notes with `import_note`, `import_raw`, `import_index`, `audition_prefix`, and `updated_at` trace fields.
  - PR #203 accepts square-bracket prefixes such as `[5.1]- ...` and imports bare/malformed-prefix rows rather than dropping them, assigning opaque synthetic `audition_prefix="row_<import_index>"` values when no source prefix parses.
  - Imported Audition rows preserve CSV order and cue timestamps, append concept and `ortho_words` intervals, strip terminal variant markers from labels, add `import_index` + `audition_prefix` trace metadata, preserve existing `source_audio_duration_sec`, log CSV detection/comment-alignment failures, and intentionally leave `ortho`, `ipa`, and `bnd` untouched for downstream jobs.
- **Razhan / HF ORTH runtime shipped and hardened**:
  - PR #213 maps provider-side Whisper language tokens `sd`/`sdh` to `fa` for Razhan/DOLMA models because their fine-tuning used `--language="persian"`; PARSE project/annotation metadata still preserves Southern Kurdish as `sdh`.
  - PR #216 adds a built-in Southern Kurdish Arabic-script ORTH decoder prime when `ortho.initial_prompt` is omitted and preserves explicit `"initial_prompt": ""` as user opt-out.
  - PR #218 changes ORTH default backend to Hugging Face Transformers `HFWhisperProvider` on `razhan/whisper-base-sdh`; STT remains faster-whisper, and legacy ORTH uses `ortho.backend="faster-whisper"` plus a local CTranslate2 model path.
  - PRs #219/#220/#222 restore HF transcription fidelity with low-level `WhisperProcessor` + `WhisperForConditionalGeneration.generate()`, 30-second full-file chunks, generated-token logprob confidence, non-16 kHz in-memory resampling, and concept-window decoding without `return_timestamps=True`.
  - PR #226 restores HF decode-level repetition guards; PR #494 moves current HF ORTH config into strict sectioned `ortho.model` / `ortho.generation` / `ortho.decoding`, rejects legacy flat HF configs with a migrator, and keeps `compute_type` / VAD as faster-whisper-only compatibility keys rather than HF runtime knobs.
  - PR #495 threads `confidence_source` (`avg_logprob` vs `constant_fallback`) and `confidence_n_tokens` through ORTH/OpenAPI/frontend consumers; PR #498 removes healthy-path HF warning/fallback by owning decode policy on `model.generation_config`, forwarding encoder attention masks, and probing that `generated.scores` is present at load.
  - PRs #299/#300 make full-file, concept-window, and per-lexeme HF ORTH suppress configured prompts by default, require explicit caller opt-in for seeded decoding, and add no-parrot regression evidence for the prompt-prefix incident.
  - Cite Razhan model usage with Hameed, Ahmadi, Hadi, and Sennrich 2025, *Automatic Speech Recognition for Low-Resourced Middle Eastern Languages*, Interspeech 2025, doi:10.21437/Interspeech.2025-2296, PDF: https://sinaahmadi.github.io/docs/articles/hameed2025ASR-ME.pdf.
- **Full-pipeline resource lifecycle and stale-lock recovery shipped**:
  - PR #227 unloads the HF ORTH model/processor and clears/synchronizes CUDA cache before wav2vec2 IPA, adds `Aligner.release()`, and enforces a tunable 4 GiB low-VRAM guard before IPA in full-pipeline runs.
  - PR #228 adds non-destructive stale `*.lock` cleanup on server startup and `POST /api/locks/cleanup`, with JSON metadata (`creator_pid`, `created_at_unix`, `speaker`), live-PID skip/manual-review semantics, legacy touch-file cleanup, and no process killing.
  - PR #229 removes the global `_LAST_ORTHO_PROVIDER` lifecycle hook and threads the ORTH provider explicitly through full-pipeline / ORTH / concept-window calls so IPA-only full-pipeline selections do not instantiate ORTH and cleanup stays locally owned.
  - PR #255 adds a host-memory preflight (`PARSE_FULL_PIPELINE_MIN_MEM_GB`) before memory-heavy full-pipeline work, returns structured `oom_suspect` job errors with memory/swap details, persists job snapshots under `PARSE_JOB_SNAPSHOT_DIR` or workspace `.parse/jobs`, recovers non-terminal snapshots after restart as `server_restarted`, and warns via `scripts/parse-run.sh` when `PARSE_COMPUTE_MODE` is unset.
- **Compare source-item and realization review shipped**:
  - PR #257 makes `concepts.csv` emit `id,concept_en,source_item,source_survey,custom_order`, parses Audition cue prefixes into `source_item`, propagates `source_survey`, and adds the dry-run-capable `set_concept_field` MCP/chat tool.
  - PRs #256/#258/#260 show source badges/sorting in `ConceptSidebar`, group concepts sharing a `source_item` into variant rows, expose A/B/C speaker-form realizations with IPA/ORTH/time/playback context, and persist per-speaker canonical picks under `manual_overrides.canonical_realizations`.
  - PR #261 classifies Audition cue families such as KLQ/EXT/JBIL into `source_survey` and extends conservative source-item backfill.
  - PR #262 fixes singleton speaker-form matching to use stable concept keys rather than emitted sidebar ids.
  - PR #263 adds manual concept merge/unmerge overrides under `manual_overrides.concept_merges`, combining underlying concept ids for comparative review without rewriting `concepts.csv` or annotation tiers.
  - PR #264 scopes concept merges to Compare mode; Annotate keeps raw concept rows independently navigable.
  - PRs #267/#268/#270/#284 ship speaker-local `AnnotationRecord.concept_tags`, omit empty concept-tag sidecars, and keep tag filters/counts scoped to the active speaker while preserving the shared tag vocabulary.
  - PRs #271/#272/#273/#278 harden source-item backfill/import so `concepts.csv` keeps the five-column schema and MCP/processed-speaker onboarding does not collapse `source_item` / `source_survey` metadata.
  - PRs #291/#292/#295/#303 add `survey-overlap.json`, `GET`/`POST /api/survey-overlap`, survey label/color controls, per-speaker choices, Current-survey copy, sidebar badges, and initial multi-survey chips; PRs #492/#496/#503 relocate active multi-survey choices to the Annotate header chip row while keeping sidebar badges/context-menu promotion.
- **Streaming responses shipped**:
  - Additive WebSocket sidecar in `python/external_api/streaming.py`
  - Dedicated port via `PARSE_WS_PORT` (default `8767`)
  - Per-job subscription endpoint: `ws://<host>:<ws_port>/ws/jobs/{jobId}`
  - Typed events: `job.snapshot`, `job.progress`, `job.log`, `stt.segment`, `job.complete`, `job.error`
  - Existing HTTP polling and callback flows remain fully supported

## MCP adapter note

- `python/adapters/mcp_adapter.py` (thin MCP entrypoint; concrete adapter modules live under `python/adapters/mcp/`) now supports `config/mcp_config.json` for explicit MCP surface selection.
- Shipped default MCP adapter surface is **67 tools** total: **63** default `ParseChatTools` from `python/ai/chat_tools.py::DEFAULT_MCP_TOOL_NAMES`, the **3** high-level `WorkflowTools` macros from `python/ai/workflow_tools.py`, plus read-only `mcp_get_exposure_mode` for self-inspection.
- `python/ai/chat_tools.py::LEGACY_CURATED_MCP_TOOL_NAMES` preserves the previous **43**-tool parse-task subset; explicit `config/mcp_config.json` → `{ "expose_all_tools": false }` keeps the adapter on that legacy **47**-tool published surface.
- Setting `expose_all_tools=true` expands `active` mode back to the full **67**-tool adapter surface, which now matches the shipped default.
- The shipped default includes the BND tools `compute_boundaries_start`, `compute_boundaries_status`, `retranscribe_with_boundaries_start`, and `retranscribe_with_boundaries_status`, plus the write/export-capable `clef_clear_data`, `csv_only_reimport`, `revert_csv_reimport`, `populate_cross_survey_links`, `export_review_data`, and `migrate_concept_suffix_pollution` tools; the underlying boundary-constrained STT compute path also accepts the alias `bnd_stt`, but `bnd_stt` is not a standalone MCP tool name in `REGISTRY`.
- The workflow macros are:
  - `run_full_annotation_pipeline`
  - `prepare_compare_mode`
  - `export_complete_lingpy_dataset`
- `run_full_annotation_pipeline` accepts optional `run_mode` (`full`, `concept-windows`, `edited-only`) and `concept_ids`; non-`full` responses include `affected_concepts` for scoped UI refresh, and empty `edited-only` runs return a structured no-op instead of starting a background job. Frontend consumers must still reload the completed speaker annotation from disk after compute completion; scoped row refresh never gates the canonical reload.
- `apply_timestamp_offset` returns `shiftedConcepts` alongside legacy `shiftedIntervals`, so user-facing copy can report distinct concepts moved without breaking interval-count consumers.
- For backward compatibility, root-level `mcp_config.json` is also accepted when `config/mcp_config.json` is absent.
- `ChatToolSpec` is the MCP metadata source of truth. MCP tools should forward the strict schema from `spec.parameters`, standard MCP annotations from `spec.mcp_annotations_payload()`, and PARSE-specific safety metadata from `meta["x-parse"] = spec.mcp_meta_payload()`.
- Task 5 adds a parallel **HTTP MCP bridge** in `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`):
  - `GET /api/mcp/exposure`
  - `GET /api/mcp/tools`
  - `GET /api/mcp/tools/{toolName}`
  - `POST /api/mcp/tools/{toolName}`
- Task 5 also adds OpenAPI docs served directly by `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`):
  - `GET /openapi.json`
  - `GET /docs`
  - `GET /redoc`
- Additive WebSocket job streaming now runs beside the HTTP server:
  - `ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}`
  - event envelope fields: `event`, `jobId`, `type`, `ts`, `payload`
  - current v1 events: `job.snapshot`, `job.progress`, `job.log`, `stt.segment`, `job.complete`, `job.error`
- Official external wrappers now live in `python/packages/parse_mcp/`.
- Mutability meanings:
  - `read_only` — inspection only; no writes or background jobs
  - `stateful_job` — starts or manages a background job that can later mutate project artifacts
  - `mutating` — can write files or otherwise change project state directly
- Agent-facing safety reasoning should read `meta["x-parse"]["preconditions"]` / `postconditions` instead of guessing from prose.

### Safety Metadata Reference

Example `meta["x-parse"]` payload exposed through MCP:

```json
{
  "mutability": "mutating",
  "supports_dry_run": true,
  "dry_run_parameter": "dryRun",
  "preconditions": [
    {
      "id": "project_loaded",
      "description": "The PARSE project root must be available and readable.",
      "severity": "required",
      "kind": "project_state"
    },
    {
      "id": "speaker_annotation_exists",
      "description": "The requested speaker must already have an annotation file to export.",
      "severity": "required",
      "kind": "file_presence"
    }
  ],
  "postconditions": [
    {
      "id": "export_file_written",
      "description": "When dryRun=false and outputPath is provided, the requested export file is written inside the project.",
      "severity": "required",
      "kind": "filesystem_write"
    }
  ]
}
```

Agent-side example:

```python
x_parse = tool.meta["x-parse"]
if any(cond["id"] == "project_loaded" for cond in x_parse["preconditions"]):
    # Load / verify project context before calling the tool.
    ...
if x_parse["supports_dry_run"]:
    # Prefer a preview call before a mutating call.
    ...
```

### Generic job observability tools

Use the generic tools when an agent needs transport-independent job inspection instead of guessing by job type.

- `jobs_list(statuses=[...], types=[...], speaker="Fail01", limit=20)`
  - lists active + recent jobs from the shared registry
- `job_status(jobId="...")`
  - returns the full generic snapshot: `type`, `status`, `progress`, `message`, `error`, `errorCode`, timestamps, `meta`, `logCount`
- `job_logs(jobId="...", offset=0, limit=50)`
  - returns structured log lines (`ts`, `level`, `event`, `message`, optional `progress`, optional `data`)

Recommended agent pattern:
1. Start a heavy job (`pipeline_run`, `stt_start`, `audio_normalize_start`, etc.)
2. Poll `job_status` for transport-neutral state
3. Inspect `locks` when coordinating speaker-scoped mutating work between humans and agents
4. Read `job_logs` when the human asks "what is it doing?" or when progress stalls
5. For HTTP-started jobs that need push completion, pass `callbackUrl` (absolute `http(s)` URL) on the job-start request so PARSE POSTs the final generic job payload on `complete` / `error`
6. For realtime progress, connect to `ws://<host>:<PARSE_WS_PORT or 8767>/ws/jobs/{jobId}` and consume the typed event stream
7. Fall back to old per-type status tools only when a workflow needs type-specific payload shaping

## Client/Server Contract Surface

All `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`) helpers have matching routes in `python/server.py` (thin HTTP orchestrator; route domains live under `python/server_routes/`):

| Client helper | Endpoint | Server status |
|---|---|---|
| `getAnnotation()` | `GET /api/annotations/{speaker}` | ✅ |
| `saveAnnotation()` | `POST /api/annotations/{speaker}` | ✅ |
| `getSttSegments()` | `GET /api/stt-segments/{speaker}` | ✅ |
| `getEnrichments()` | `GET /api/enrichments` | ✅ |
| `saveEnrichments()` | `POST /api/enrichments` | ✅ |
| `importConceptsCsv()` | `POST /api/concepts/import` | ✅ Multipart upload |
| `importTagCsv()` | `POST /api/tags/import` | ✅ Multipart upload |
| `getTags()` | `GET /api/tags` | ✅ |
| `mergeTags()` | `POST /api/tags/merge` | ✅ |
| `saveLexemeNote()` | `POST /api/lexeme-notes` | ✅ |
| `importCommentsCsv()` | `POST /api/lexeme-notes/import` | ✅ Multipart upload |
| `getConfig()` | `GET /api/config` | ✅ |
| `updateConfig()` | `PUT /api/config` | ✅ |
| `getPipelineState()` | `GET /api/pipeline/state/{speaker}` | ✅ |
| `getAuthStatus()` | `GET /api/auth/status` | ✅ |
| `startAuthFlow()` | `POST /api/auth/start` | ✅ |
| `pollAuth()` | `POST /api/auth/poll` | ✅ (required to drive Codex device-token exchange; `getAuthStatus` only reads cached state) |
| `saveApiKey()` | `POST /api/auth/key` | ✅ |
| `logoutAuth()` | `POST /api/auth/logout` | ✅ |
| `startSTT()` | `POST /api/stt` | ✅ |
| `pollSTT()` | `POST /api/stt/status` | ✅ |
| `startNormalize()` | `POST /api/normalize` | ✅ ffmpeg loudnorm pipeline |
| `pollNormalize()` | `POST /api/normalize/status` | ✅ |
| `onboardSpeaker()` | `POST /api/onboard/speaker` | ✅ Multipart upload, background job |
| `pollOnboardSpeaker()` | `POST /api/onboard/speaker/status` | ✅ |
| `detectTimestampOffset()` | `POST /api/offset/detect` | ✅ |
| `detectTimestampOffsetFromPair()` / `detectTimestampOffsetFromPairs()` | `POST /api/offset/detect-from-pair` | ✅ |
| `pollOffsetDetectJob()` | `POST /api/compute/{offset_detect or offset_detect_from_pair}/status` | ✅ typed compute poll via `pollCompute()` |
| `applyTimestampOffset()` | `POST /api/offset/apply` | ✅ |
| `searchLexeme()` | `GET /api/lexeme/search` | ✅ |
| `requestSuggestions()` | `POST /api/suggest` | ✅ |
| `startChatSession()` | `POST /api/chat/session` | ✅ |
| `getChatSession()` | `GET /api/chat/session/{id}` | ✅ |
| `runChat()` | `POST /api/chat/run` | ✅ |
| `pollChat()` | `POST /api/chat/run/status` | ✅ |
| `startCompute()` | `POST /api/compute/{type}` | ✅ Dynamic dispatch |
| `pollCompute()` | `POST /api/compute/{type}/status` | ✅ |
| `cancelComputeJob()` | `POST /api/compute/{jobId}/cancel` | ✅ Cooperative cancel registry; ORTH can return `partial_cancelled` |
| `listActiveJobs()` | `GET /api/jobs/active` | ✅ |
| `getJobLogs()` | `GET /api/jobs/{jobId}/logs` | ✅ |
| `getLingPyExport()` | `GET /api/export/lingpy` | ✅ |
| `getNEXUSExport()` | `GET /api/export/nexus` | ✅ placeholder/data-dependent output |
| `spectrogramUrl()` | `GET /api/spectrogram` | ✅ URL builder for image endpoint |
| `getContactLexemeCoverage()` | `GET /api/contact-lexemes/coverage` | ✅ |
| `startContactLexemeFetch()` | `POST /api/compute/contact-lexemes` | ✅ |
| `getClefConfig()` | `GET /api/clef/config` | ✅ |
| `saveClefConfig()` | `POST /api/clef/config` | ✅ |
| `getClefCatalog()` | `GET /api/clef/catalog` | ✅ |
| `getClefProviders()` | `GET /api/clef/providers` | ✅ |
| `getClefSourcesReport()` | `GET /api/clef/sources-report` | ✅ |
| `saveClefFormSelections()` | `POST /api/clef/form-selections` | ✅ |
| No frontend helper yet | `POST /api/clef/clear` | ✅ Direct HTTP + MCP/chat tool `clef_clear_data`; add a `src/api/contracts/*` helper before any frontend UI calls it |
| No frontend helper yet | `POST /api/locks/cleanup` | ✅ Admin/stale-lock cleanup route; startup cleanup also runs server-side |
| `listModels()` / `getModel()` | `GET /api/models`, `GET /api/models/{id}` | ✅ Desktop model registry read routes (bundled + user models) |
| `installModelPack()` / `installModelFromHf()` | `POST /api/models/install` | ✅ Job-tracked (202 + `{jobId}`, compute_type `model_install`); multipart pack upload OR JSON `{hfRepoId, stage, format, name?}` |
| `deleteModel()` | `DELETE /api/models/{id}` | ✅ Synchronous; USER models only (bundled are read-only and refused); returns `{id, deleted}` |
| `getModelBinding()` / `setModelBinding()` | `GET /api/models/binding`, `POST /api/models/binding` | ✅ Per-project stage→model binding in `project.json` `models` key; response wraps `{binding, project}`; POST `{stage, modelId}` (validated; `modelId` null clears) |

**Rule:** Keep this table current. Every new client helper must have a matching server route before merge.

## Deferred Validation Backlog

The following validation items remain important, but they are **not hard blockers for current implementation work**:

- **C5:** LingPy TSV export verification (columns + row counts in browser)
- **C6:** Full browser regression checklist (Annotate waveform/regions/STT + Compare grid/tags/nav)
- **Current policy:** if Lucas asks for work on other PR stages, do that work. Keep C5/C6 on a deferred to-test list and run them in the order of actual testing once onboarding/import and end-to-end flows are ready.
- **C7 / legacy cleanup:** destructive cleanup is no longer mechanically blocked on C5/C6 signoff, but it still requires a scoped PR, rollback discipline, and Lucas review/merge.

## Branch + Worktree Policy

### Canonical clone path
- **Canonical PARSE clone:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
  - Directory name is historical (preserved post-cutover to avoid breaking worktrees and `parse-*` helper scripts).
  - `git remote -v` must show `origin git@github.com:ArdeleanLucas/PARSE.git` (the canonical post-cutover repo) before any work.
  - This is the only PARSE clone on the PC. Pre-cutover oracle and archive clones have been removed; their history is preserved in cold-storage git bundles and workspace rsync backups. Treat all cutover-era backups as read-only evidence, not as live runtime roots.

### Active development rule
- New work branches from `origin/main` in the canonical clone, in a worktree under `/home/lucas/gh/worktrees/<agent>-<slug>/` (full recipe in §Parallel work via worktrees above).
- Use `parse-worktree-new <slug>` to create worktrees; use `parse-worktree-clean` to remove merged ones.
- The canonical clone at `/home/lucas/gh/tarahassistant/PARSE-rebuild` MUST stay on `main`. Never `git checkout -b` inside it; always create a worktree first. See §Parallel work via worktrees for the recipe and rationale (`parse-run` reads from this clone).
- After your PR merges, the post-merge cleanup recipe in §Parallel work via worktrees is mandatory, not optional. If the canonical clone is on any branch other than `main` when you declare done, the handoff is incomplete.
- Do not branch from pre-cutover archive bundles or stale local refs without an explicit reason; cutover-era history is read-only.

## Ownership + Coordination

Historical split remains useful for boundaries:

- ParseBuilder domain: Annotate + shared platform
- Oda domain: Compare mode components/stores/hooks

However, on current `main`, coordinate shared-surface edits carefully.

### Shared surfaces requiring coordination before commit
- `src/api/client.ts` — barrel only; coordinate the underlying `src/api/contracts/**` change set, not just the re-export line
- `src/api/types.ts`
- `python/server.py` — thin orchestrator; most route changes should happen in `python/server_routes/**`
- `python/ai/chat_tools.py` — registry/orchestrator; most tool changes should happen in `python/ai/tools/**` or `python/ai/chat_tools/**`
- `python/adapters/mcp_adapter.py` — entrypoint only; most MCP changes should happen in `python/adapters/mcp/**`


## Coordinator handoff convention (2026-04-26)

New queued work for `parse-front-end`, `parse-back-end`, and `parse-coordinator` is tracked under repo-local handoff files instead of merge-to-main queue-prompt PRs. Historical on-disk directories remain `parse-builder/`, `parse-back-end/`, and `parse-gpt/` for compatibility.

### Canonical queue location

```text
.hermes/handoffs/<agent>/<YYYY-MM-DD>-<slug>.md
```

### Rules

- New coordinator task queueing should go into `.hermes/handoffs/`, not `docs: queue <agent> next task` PRs.
- Handoff front matter must record at minimum: `agent`, `queued_by`, `queued_at`, `status`, and optional `related_prs`.
- Lifecycle is file-based: `queued` → `in-progress` → `done` (move completed items into `.hermes/handoffs/<agent>/done/`).
- Historical queue-prompt PRs remain part of the audit trail, but they are no longer the preferred mechanism for staging the next task.
- Current open queue PRs that predate this convention can finish their immediate lifecycle, but future queue churn should not go through main-branch docs PRs.

### Closeout precondition

Before any agent (any lane) declares a handoff done, they MUST verify the canonical clone at `/home/lucas/gh/tarahassistant/PARSE-rebuild` is on `main` and synchronized with `origin/main`:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild && git status --short --branch
# Expected output: ## main...origin/main
```

A non-`main` HEAD means cleanup was skipped. A stale local worktree or feature branch for the just-merged PR means cleanup is incomplete. Finish the cleanup before reporting completion.

## Safe Work Now (current priority)

- Keep canonical PARSE docs aligned with the post-cutover repo, not archived rebuild/oracle language.
- Treat concept-scoped pipeline run modes as shipped: preserve `run_mode`, `concept_ids`, `affected_concepts`, no-op `edited-only` semantics, and post-compute canonical disk reload across HTTP, MCP, React, and `parse_mcp` docs.
- Treat the Audition CSV import path from PRs #198/#200/#201/#203/#204/#207/#208 as shipped: marker CSV detection, CSV-order concept/`ortho_words` interval seeding, integer-only concept-id resolution, `commentsCsv` row-index note import, bracket/bare-row parsing, trace-field round trips, save-time concept-id enforcement, and identity-only frontend concept matching are current behavior.
- Treat the 2026-05-01 HF ORTH/default-runtime wave as shipped: ORTH defaults to HF Transformers Razhan, STT stays faster-whisper, HF concept windows resample/decode without timestamp-return drift, decode repetition guards are active, batch cancel posts backend cancel, cooperative ORTH cancel may persist `partial_cancelled`, full-pipeline ORTH unloads before IPA, and stale speaker-lock cleanup is server/admin-side.
- Maintain parity artifacts under `parity/` and keep C5/C6 browser/workstation validation explicit rather than implied by harness success.

## Do Not Touch

- Avoid broad incidental churn in `src/components/compare/*`; edit compare components when required by the active stage and keep changes scoped/test-backed
- `config/sil_contact_languages.json` directly (runtime output file)
- Broad destructive cleanup without a scoped PR, rollback plan, and Lucas review/merge

## Frontend Rules (hard constraints)

These apply to every `src/` file. Violation = stop and fix before merge.

**API & state**
1. **No bare `fetch()` calls.** Every API call goes through `src/api/client.ts` (barrel; concrete helpers live under `src/api/contracts/*.ts`).
2. **No `window.PARSE` references.** The old global namespace is dead in React.
3. **No `localStorage` reads/writes** except inside `tagStore.persist()` and `tagStore.hydrate()`.
4. **Zustand is the only state for data.** `useState` is allowed only for pure UI state (modal open/close, which tab is active).
5. **`enrichmentStore.save()` is the only write path for enrichment data.** No direct `POST /api/enrichments` from components.
6. **`tagStore.persist()` after every mutation.** A tag that is not persisted is lost on page reload.

**Data invariants**
7. **Timestamps are controlled data, not disposable AI output.** `start` and `end` on `AnnotationInterval` must not be normalized or silently rewritten. They may change only through explicit user-reviewed retime paths (`saveLexemeAnnotation`, scoped drag retime, offset correction) that mark affected intervals `manuallyAdjusted` and preserve concept IDs.
8. **Concept IDs are stable identifiers.** Never normalize, trim, lowercase, or transform. The entire pipeline (annotations, enrichments, LingPy, BEAST2) breaks silently if IDs drift.

**Code quality**
9. **TypeScript strict mode.** Every file must compile with `npx tsc --noEmit`.
10. **No `any` types** unless unavoidable. If you use `any`, add an inline comment explaining exactly why.
11. **Prefer classes / Tailwind / CSS modules over inline styles.** Inline `style={{…}}` is allowed for values that are genuinely dynamic (computed widths, progress bars) — don't use it as a shortcut for static layout. Existing files with heavy inline styles (e.g. `ParseUI.tsx`, shared primitives) should migrate as they're touched, not via broad churn.
12. **No emoji in the UI.** Text labels only — this is a fieldwork research tool.
13. **Every feature component and hook has a co-located test file.** "Feature" = anything under `src/components/annotate/`, `src/components/compare/`, `src/hooks/`. Shared primitives under `src/components/shared/` are exempt. The current observed frontend floor in Test Gates below (≥514 passing as of PR #224) is the enforced check; this rule is the target for new features.


## Backend rules — long-running endpoints must be job-tracked (added 2026-05-10)

Any HTTP endpoint whose typical-case latency exceeds **~1 second** of synchronous work MUST be job-tracked: return 202 + `{jobId}` immediately, run the work in a background compute runner via `_create_job` + `_launch_compute_runner`, and emit progress via `_set_compute_progress(job_id, pct, message=...)` as work advances.

**Concrete checklist (all four must hold before the PR is approved):**

1. The route handler returns `JsonResponseSpec(status=ACCEPTED, payload={"jobId": ...})` on the success path. **`jobId: null` is a smell.** If you find yourself returning a null jobId, either the work fits inside one HTTP request (rare; prove it with a p95 measurement) or you are skipping the job system and breaking the FE progress bar.
2. The compute function is registered in the dispatch table at `python/server_routes/jobs.py` (both ~line 357 and ~line 963 — they are mirror sites). Use the canonical 4-alias snake/kebab/short pattern that `full_pipeline` uses (`{'foo_bar', 'foo-bar', 'foobar'}`).
3. The runner emits `_set_compute_progress` per logical work unit so a 96-iteration loop reports 96 monotonically increasing progress events. Missing per-iteration progress means the header bar shows nothing during a long block — same UX bug as a non-job endpoint.
4. The FE consumer calls `startCompute(...)` / `pollCompute(...)` from `src/api/contracts/chat-and-generic-compute.ts` — never a bare `apiFetch` against the start endpoint. Bare `apiFetch` blocks the request and bypasses the existing job-poll hook stack. **If you add a UI affordance to a Run dialog that already has job-tracked modes, the new mode MUST also be job-tracked.** Cross-mode UX consistency is enforced by this rule, not by review luck.

**Failure mode that motivated this rule:** PR #321 added `/api/lexemes/rerun-by-tag` as a synchronous bulk endpoint that returned `jobId: null`. PR #323 then wired a `Tagged-only` run mode into the same Run dialog as `Full audio` and `All concept windows` (both of which go through `/api/compute/full_pipeline` and ARE job-tracked). Result: same dialog, same look, but Tagged-only silently blocked the FE for the duration of the per-concept loop with zero header progress. On a 96-tagged-concept Khan02 run on 2026-05-09 this was a 29-second silent freeze, made worse by the backend reloading the HF Whisper provider per concept (no caching across the loop). The fix converted the endpoint to job-tracked and cached the provider across the worker thread.

Neither #321 nor #323 was wrong in isolation. The combination broke a UX invariant that nobody had codified. This rule codifies it.

**Cheap pre-merge checks for any new compute-style endpoint:**

```bash
# 1. Does the success path return a non-null jobId?
grep -n 'jobId.*None\|"jobId": null\|jobId.*null' python/app/http/<your_handler>.py
# Should return zero matches on the success path.

# 2. Is the compute_type registered in the dispatch table at both sites?
grep -n '<your_compute_type>' python/server_routes/jobs.py
# Should return two matches (~line 357 and ~line 963).

# 3. Does the runner emit progress more than once?
grep -c '_set_compute_progress' python/server_routes/<your_runner>.py
# Should be > 1 for any loop-based runner.

# 4. Does the FE consumer use startCompute, not bare apiFetch?
grep -n 'apiFetch.*compute\|startCompute' src/api/contracts/<your_caller>.ts
# Should show startCompute, not raw apiFetch against the start endpoint.
```

If any of these checks fails, the PR is not done.


## Backend rules — chunking and subprocess isolation pointers (added 2026-05-13)

Long full-mode ORTH/STT chunking is governed by `PARSE_ORTH_DEFAULT_CHUNK_MINUTES=10` and `PARSE_STT_DEFAULT_CHUNK_MINUTES=10`; IPA does not chunk by audio duration, but `PARSE_IPA_SHRINK_WARN_THRESHOLD_SEC=60` guards destructive IPA overwrite reruns. Full-file STT, ORTH, and IPA run memory-heavy stages in isolated subprocesses via `_run_in_isolated_subprocess`; see `docs/architecture/compute.md` for the canonical contract.

Drift guard: `python/test_docs_compute_env_vars.py` ties `docs/architecture/compute.md` to the chunking env vars and top-level subprocess wrap names. Adding a chunking env var or top-level subprocess wrap requires updating both the doc and that test's expected set.

## Backend rules — compute children must tee stderr, not redirect (added 2026-05-10)

Any `multiprocessing.get_context("spawn")` child entry that opens a per-PID/per-job logfile MUST tee output instead of replacing the inherited streams. Use `install_child_tee(log_path)` from `python/shared/subprocess_tee.py` so stdout/stderr still reach parent fd 1/2 while the log remains available for OOM/segfault tails.

This rule came from PR #334's lexeme-rerun stdout fence regression, fixed in PR #339 and generalized in PR #340. Replacing `sys.stderr` silently hides live `[ORTH]`/`[IPA]`/`[STT]`/`[WORKER]` progress from the parent terminal.

Only add a child logfile when the parent tails it for crash diagnostics (for example `_read_child_log_tail`); pure progress-streaming children should inherit fd 2 directly. If a new child still contains `sys.stderr = open(...)`, the PR is not done.

## Test Gates (pre-push)

Run both before pushing PARSE frontend changes:

```bash
npx vitest run
./node_modules/.bin/tsc --noEmit
```

For backend/server changes, also run the relevant `PYTHONPATH=python python3 -m pytest ...` target and `uvx ruff check python/ --select E9,F63,F7,F82` before pushing. Current main after PR #224 validated at **83 files / 514 frontend tests** with clean TypeScript and build; current backend full sweep after MC-419-A validated at **1733 passed, 6 skipped, 1 warning, 3 subtests passed** plus clean `uvx ruff check python/ --select E9,F63,F7,F82`. If those counts shift, explain why in the PR.

**Full sweep before push for backend-touching PRs.** When a PR adds or modifies any file under `python/`, final verification must include the full backend sweep:

```bash
PYTHONPATH=python python3 -m pytest python/ -q
```

A narrow `-k` selector is appropriate during iteration, but never as the final pre-push gate. Do not deselect `test_ortho_section_defaults_cascade_guard` or `test_ortho_explicit_override_beats_defaults`: MC-419-A re-ran the full backend sweep in order and proved both tests pass without the old workaround. MC-384-Y codifies the broader principle after the MC-384-X/Y regression cycle: a narrow selector went green while the broader sweep exposed downstream `test_compute_speaker_ortho.py` failures.

## Baseline Architecture

- Frontend: React 18 + TypeScript + Vite + Zustand
- Backend: Python server on `127.0.0.1:8766`
- Data: speaker annotations JSON + enrichments + LingPy export pipeline

---

If pivot status changes (new milestone completion, gating updates, ownership shifts), update this file immediately to prevent stale coordination instructions.
