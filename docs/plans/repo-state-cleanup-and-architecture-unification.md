# PARSE Repository State Cleanup and Architecture Unification Plan

> **For Hermes:** Execute from the lowercase clone `/home/lucas/gh/ardeleanlucas/parse` unless Lucas explicitly decides otherwise. Do **not** merge to `main` directly. Open PRs; **Lucas must merge them**.

**Goal:** Get PARSE into a clean post-pivot state with one canonical active repo, explicit React-vs-legacy boundaries, a defensible branch cleanup sequence, and a gated path to removing legacy HTML/JS.

**Architecture:** PARSE is currently hybrid. The React + Vite app is live at `index.html` + `src/`, while legacy `parse.html`, `compare.html`, and `js/` still remain on `main` and are still advertised by the Python server and README. Cleanup must happen in phases so thesis-critical workflows are not broken before C5/C6 validation.

**Tech Stack:** Git/GitHub, React 18, Vite, TypeScript, Zustand, Python `server.py`, legacy static HTML/JS.

---

## Current State Summary

- **Canonical active repo for now:** `/home/lucas/gh/ardeleanlucas/parse`
- **Archive/divergent clone:** `/home/lucas/gh/ArdeleanLucas/PARSE`
  - Its `main` currently points at `archive/main`, not `origin/main`
  - Do not trust it for current branch truth until Lucas explicitly approves a reset/repoint decision
- **Current GitHub branches:**
  - `main`
  - `feat/annotate-react`
  - `feat/compare-react`
  - `feat/parse-react-vite`
  - `fix/onboarding-open-ai-assistant`
- **Merged PRs already on `main`:**
  - PR #2 — `feat/parse-react-vite`
  - PR #3 — `fix/onboarding-open-ai-assistant`
- **Legacy is still present on `main`:**
  - `parse.html`
  - `compare.html`
  - `js/`
- **Legacy is still user-facing in docs/server output:**
  - `README.md` still points users to `/parse.html` and `/compare.html`
  - `python/server.py` startup output still prints `/parse.html` and `/compare.html`
  - additional docs/scripts may still assume the legacy flow
- **Policy conflict to reconcile:**
  - current `AGENTS.md` still treats the uppercase clone/worktree model as canonical
  - current `AGENTS.md` also warns against touching `python/server.py` pre-C6 except for CLEF endpoints
- **Gate:** C7 cleanup is still blocked until Lucas explicitly clears **C5** and **C6**.

---

## Non-Negotiable Rules

1. **No direct merge to `main` by Hermes.**
   - If a code/doc change is needed, Hermes opens a PR.
   - **Lucas merges it.**
2. **No legacy deletion before C5/C6 signoff.**
3. **No branch deletion without Lucas approval.**
4. **No force-reset of the uppercase archival clone without Lucas approval.**
5. **Lowercase repo is the source of truth for active dev until policy docs are explicitly updated.**
6. **Any destructive cleanup must have a rollback point recorded first.**

---

## Responsibility Split

| Area | Hermes | Lucas |
|---|---|---|
| Repo audits | Yes | Optional review |
| Doc/code edits | Yes | Reviews via PR |
| PR creation | Yes | N/A |
| Merge to `main` | No | **Yes** |
| Branch deletion | Prepare recommendation | **Approve / execute or authorize** |
| Uppercase clone reset/repoint | Recommend only | **Approve** |
| C5 signoff | Support / verify evidence | **Yes** |
| C6 signoff | Support / verify evidence | **Yes** |
| C7 destructive cleanup authorization | Recommend | **Yes** |

---

## Phase 0 — Preflight and Policy Reconciliation

### Objective
Remove ambiguity before any cleanup work starts.

### Task 0.1 — Reconcile repo-path policy

**Objective:** Make active-repo guidance consistent across planning docs.

**Files:**
- Modify: `AGENTS.md`
- Optional modify: `README.md`
- Optional modify: relevant docs under `docs/plans/`

**Required change:**
- State that active execution currently uses `/home/lucas/gh/ardeleanlucas/parse`
- State that `/home/lucas/gh/ArdeleanLucas/PARSE` is currently archive/divergent unless Lucas later repoints it
- Explicitly note that `python/server.py` messaging cleanup is allowed as a non-destructive documentation/UX fix, but legacy removal remains blocked until C5/C6

**Verification:**
- Read updated docs and confirm there is no longer a canonical-path contradiction

**Needs Lucas merge?** Yes — PR required.

---

### Task 0.2 — Inventory all legacy references

**Objective:** Build the full list of places that still advertise or depend on legacy entrypoints.

**Files:**
- Create: `docs/plans/legacy-entrypoint-inventory.md`

**Search scope:**
- `README.md`
- `AGENTS.md`
- `CODING.md`
- `python/server.py`
- `start_parse.sh`
- `Start Review Tool.bat`
- `desktop/`
- `docs/`
- any launchers or scripts that mention `parse.html`, `compare.html`, `localhost:8766`, or legacy JS assumptions

**Verification:**
- Inventory file lists exact paths and whether each reference must be changed in Phase 3 or Phase 5

**Needs Lucas merge?** Yes — PR required.

---

### Task 0.3 — Record rollback and ancestry facts

**Objective:** Ensure destructive steps can be reversed and branch decisions are evidence-based.

**Files:**
- Create: `docs/plans/repo-cleanup-preflight.md`

**Required contents:**
- current `origin/main` SHA
- current remote branch list
- ancestry / ahead-behind notes for:
  - `feat/annotate-react`
  - `feat/compare-react`
  - `feat/parse-react-vite`
  - `fix/onboarding-open-ai-assistant`
- note whether each branch is cleanly merged, historical, or ambiguous
- rollback point recommendation for pre-C7 and pre-deletion states

**Verification:**
- File is sufficient for Lucas to approve or reject destructive steps later

**Needs Lucas merge?** Yes — PR required.

---

## Phase 1 — Canonicalize Local Repo Usage

### Objective
Make it impossible to accidentally inspect or run the wrong local clone.

### Task 1.1 — Decide fate of uppercase archival clone

**Objective:** Explicitly preserve or repoint the uppercase clone.

**Files:**
- No repo-file edits required until Lucas decides.

**Options:**
- **Option A: Preserve as archive clone**
  - Keep it unchanged
  - Document that it tracks `archive/main`
- **Option B: Repoint/reset to `origin/main`**
  - Only after Lucas approves destructive reset behavior
  - Then make it match the active lowercase clone

**Recommendation:**
- Prefer **Option A for now** unless Lucas wants a strict single-clone workflow.

**Needs Lucas action?** Yes — repo-maintenance decision.

---

## Phase 2 — Audit `feat/compare-react` Before Any Deletion

### Objective
Decide whether `feat/compare-react` is stale residue or still meaningful.

### Task 2.1 — Produce a compare-branch audit note

**Objective:** Determine whether the branch-only divergence should be preserved, rebased, or discarded.

**Files:**
- Create: `docs/plans/compare-branch-audit.md`

**Required analysis:**
1. Inspect `origin/main..origin/feat/compare-react`
2. Identify whether the branch-only commit is semantically meaningful or just stale merge residue
3. Compare branch intent against current `main`
4. State one of three recommendations:
   - delete
   - keep as historical lane
   - revive/rebase intentionally

**Verification:**
- Audit note gives Lucas enough evidence to approve or reject deletion

**Needs Lucas permission?**
- Audit: no
- Deletion or revival after audit: yes

---

## Phase 3 — Non-Destructive Messaging and Documentation Cleanup

### Objective
Stop misleading users while legacy still exists.

### Task 3.1 — Update README architecture and entrypoints

**Objective:** Make React dev entrypoints explicit and label legacy pages correctly.

**Files:**
- Modify: `README.md`

**Required changes:**
- Update dev workflow to state React dev uses:
  - `http://localhost:5173/`
  - `http://localhost:5173/compare`
- Label Python-served legacy pages as fallback/legacy only:
  - `http://localhost:8766/parse.html`
  - `http://localhost:8766/compare.html`
- Update any sections that still describe PARSE as exclusively “no build step” or exclusively legacy-HTML based
- Note that full legacy removal is gated on C5/C6 → C7

**Verification:**
- README no longer implies legacy is the primary architecture

**Needs Lucas merge?** Yes — PR required.

---

### Task 3.2 — Update server startup messaging

**Objective:** Stop `python/server.py` from implying legacy is the only correct entrypoint.

**Files:**
- Modify: `python/server.py`

**Required changes:**
- Keep printing legacy URLs if needed for fallback access
- Also print React dev guidance, e.g.:
  - React dev: `http://localhost:5173/`
  - React compare: `http://localhost:5173/compare`
- Explicitly label `/parse.html` and `/compare.html` as legacy entrypoints

**Verification:**
- Start server locally
- Confirm startup output clearly distinguishes React dev vs legacy fallback

**Needs Lucas merge?** Yes — PR required.

---

### Task 3.3 — Update secondary docs and launchers inventory-derived references

**Objective:** Reduce lingering ambiguity outside the root README.

**Files:**
- Modify: `AGENTS.md`
- Modify: `CODING.md` if needed
- Modify: relevant files identified in `docs/plans/legacy-entrypoint-inventory.md`
- Possibly modify: `start_parse.sh`, `Start Review Tool.bat`, desktop docs, launcher notes

**Required change:**
- Any surviving legacy references must be explicitly labeled as temporary / pre-C7
- Any React dev workflow references must point to `:5173`

**Verification:**
- Inventory file can be checked off item-by-item

**Needs Lucas merge?** Yes — PR required.

---

## Phase 4 — Clear C5 and C6 Before Any Legacy Removal

### Objective
Reach the cleanup gate honestly, not aspirationally.

### Task 4.1 — C5 LingPy export signoff

**Objective:** Lucas verifies LingPy TSV export correctness in browser.

**Verification target:**
- Row counts correct
- Columns correct
- Export reflects current React workflow outputs

**Needs Lucas action?** Yes — manual signoff.

---

### Task 4.2 — C6 browser regression signoff

**Objective:** Lucas verifies full user workflow in the React app.

**Coverage:**
- Annotate waveform / regions / STT / onboarding / chat
- Compare grid / tags / nav / import / export affordances

**Needs Lucas action?** Yes — manual signoff.

---

## Phase 5 — C7 Legacy Removal and True Architecture Unification

### Objective
Make PARSE expose only the new architecture.

### Task 5.1 — Decide build artifact strategy for Python-served frontend

**Objective:** Specify exactly what the Python server will serve after legacy removal.

**Files:**
- Modify: `README.md`
- Modify: `python/server.py`
- Modify: startup/build docs as needed

**Required decision:**
- Preferred path: `npm run build` produces `dist/`
- Python server serves the built frontend from `dist/` for production-like/local-server usage
- Vite `:5173` remains the dev-only workflow

**Verification:**
- Decision is documented before any legacy file deletion PR is opened

**Needs Lucas merge?** Yes — PR required.

---

### Task 5.2 — Remove legacy frontend files and switch canonical serving

**Objective:** Delete the no-longer-authoritative legacy UI and make the Python server serve the React build.

**Files:**
- Delete: `parse.html`
- Delete: `compare.html`
- Delete: `js/`
- Modify: `python/server.py`
- Modify: any file needed to support built frontend serving

**Preconditions:**
- Lucas has explicitly cleared C5 and C6
- rollback point recorded in `docs/plans/repo-cleanup-preflight.md`

**Acceptance criteria:**
- `npm run build` succeeds and produces `dist/index.html` and required assets
- Python server serves the built frontend for non-API routes
- direct GET `/` returns the React app shell
- direct GET `/compare` returns the React app shell via SPA fallback
- `/api/*` routes still return JSON as before
- audio/static behavior needed by thesis workflows still works
- legacy `parse.html` / `compare.html` references are removed or intentionally redirected

**Needs Lucas permission?** Yes — destructive cleanup.
**Needs Lucas merge?** Yes — PR required.

---

### Task 5.3 — Remove remaining legacy references from docs and launchers in the same unification wave

**Objective:** Finish cleanup so docs match reality on the same architecture cutover.

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CODING.md` if needed
- Modify: launchers/start scripts
- Modify: relevant docs under `docs/`

**Verification:**
- No user-facing docs imply `parse.html` / `compare.html` are the primary interface
- No launcher still assumes legacy HTML entrypoints are canonical

**Needs Lucas merge?** Yes — PR required.

---

## Phase 6 — Branch Cleanup After Successful Merge/Signoff

### Objective
Prune the branch list only after the repo is in a stable, documented state.

### Task 6.1 — Delete clearly historical merged branches

**Candidate branches:**
- `fix/onboarding-open-ai-assistant`
- `feat/parse-react-vite`
- `feat/annotate-react`

**Why they should go:**
- They are historical lanes or merged fix branches already subsumed by `main`
- Keeping them makes GitHub look more architecturally fragmented than it should

**Verification before deletion:**
- Confirm each is merged/subsumed by current `main`
- Confirm Lucas still wants them pruned

**Needs Lucas permission?** Yes — destructive action.

---

### Task 6.2 — Resolve `feat/compare-react`

**Objective:** Delete, preserve, or revive it intentionally based on the Phase 2 audit.

**Needs Lucas action?** Yes — explicit decision required.

---

## Proposed Execution Order

1. **PR: Phase 0 preflight + policy reconciliation**
2. **Audit `feat/compare-react` and give Lucas a delete/keep/revive recommendation**
3. **PR: Phase 3 non-destructive README / AGENTS / server / doc messaging cleanup**
4. **Lucas merges those non-destructive PRs to `main`**
5. **Lucas clears C5**
6. **Lucas clears C6**
7. **PR: Phase 5 C7 unification (build serving + legacy removal + launcher/doc cleanup)**
8. **Lucas merges the C7 PR to `main`**
9. **After stable merge/signoff, delete clearly historical branches with Lucas approval**

---

## Lucas Decisions Required

1. Whether the uppercase clone should remain archive-only or later be reset to track `origin/main`
2. Approval to merge any non-destructive policy/docs/server cleanup PRs
3. Final decision on whether `feat/compare-react` should be preserved, deleted, or revived after audit
4. C5 signoff
5. C6 signoff
6. Approval for destructive C7 cleanup PR merge
7. Approval for branch deletions

---

## Definition of Proper Final State

PARSE is in a proper final state when all of the following are true:

- One local clone is treated as canonical for active development
- The GitHub branch list is pruned to active work only
- README, AGENTS, server output, and launchers no longer mislead users toward legacy entrypoints
- Lucas has signed off on C5 and C6
- Legacy `parse.html`, `compare.html`, and `js/` are removed
- Python server serves the current React frontend as the canonical non-dev UI
- `/` and `/compare` resolve correctly after cutover
- `main` is the obvious single source of truth
