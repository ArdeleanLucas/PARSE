# parse-gpt — next task: close baseline, score progress, clean coordination state

**Lane:** Coordinator
**Date queued:** 2026-04-26
**Rebuild oracle SHA at queue time:** `f9aa3db1aa`
**Live oracle SHA at queue time:** `ArdeleanLucas/PARSE@0951287a81`
**Branch from:** `origin/main`
**Estimated PR count:** 4 (independent; can be parallelized — but PR 1 must land before PRs 2/3/4 are useful)

---

## Why this task

The rebuild has merged 49 PRs in ~24 hours and is producing real structural progress on the backend (server.py down 12.8%) and modest progress on the frontend (ParseUI.tsx down 17.1%). But three coordination artifacts that the rebuild plan calls out as preconditions are still open:

1. **`docs/plans/option1-phase0-shared-contract-checklist.md` is an unsigned template.** Every checkbox is empty. Both implementation lanes have been running against an implicit oracle baseline rather than a frozen, recorded one. This is the gate that the plan itself names a "hard blocker" before parallel implementation. (See §1 of that file: *"Phase 0 is a hard blocker. Agent A and Agent B do not begin divergent implementation until this checklist is complete and explicitly signed off."*) That gate has been ignored.
2. **`.hermes/state`, `.hermes/handoffs`, `.hermes/reports`** were last touched 2026-04-25 23:41, before most of the merge wave. Coordination state is stale or invisible. Anything new written to `.hermes/automation/` is gitignored.
3. **No parity-evidence pass has been run.** `docs/plans/option1-parity-inventory.md` defines a P0/P1/P2 evidence contract; zero P0 surfaces have evidence recorded against them.

This task closes those three gaps and produces a published progress scorecard so that future task assignment is grounded in numbers rather than vibes.

A separate, lower-priority but still important task: PR-queue churn. ~10 of the 49 merged PRs are `docs: queue <agent> next task` prompts that inflate the merge count without moving the rebuild forward. This task moves that queueing mechanism out of the main-branch PR stream.

---

## Scope

### In scope (4 PRs, in order of priority)

1. **PR 1: Sign Phase 0 baseline.** Fill in the empty checkboxes in `docs/plans/option1-phase0-shared-contract-checklist.md` with the actual recorded baseline (oracle SHA, fixture set, frontend/backend gate evidence, known quirks).
2. **PR 2: Publish progress scorecard.** Add `docs/reports/2026-04-26-rebuild-progress-scorecard.md` using the `parse-rebuild-progress-scorecard` skill methodology — separates monolith reduction, parity evidence coverage, and desktop-distribution readiness as three distinct scores.
3. **PR 3: Run a single P0 parity-evidence pass on Annotate.** Use `parse-rebuild-annotate-parity-audit` skill. Add `docs/reports/2026-04-26-annotate-parity-evidence.md` recording oracle vs rebuild behavior across the P0 Annotate flows listed in `option1-parity-inventory.md` §5.1.
4. **PR 4: Move task-queueing out of main-branch PRs.** Establish `.hermes/handoffs/` as the canonical queue location, document the new convention in `AGENTS.md`, and close the loop by retroactively listing the 10 already-merged queue-prompt PRs in a single index doc so the audit trail isn't lost.

### Out of scope

- Implementation work in `src/` or `python/` — Agent A (parse-builder) and Agent B (parse-back-end) own those.
- Reviewing or merging open implementation PRs — that is the coordinator's *next* task after these 4 land.
- Changes to `option1-separate-rebuild-to-option3-desktop-platform.md`, `option1-two-agent-parallel-rebuild-plan.md`, `option1-parity-inventory.md` — these are stable plan docs.
- Touching `.github/workflows/`.

---

## PR 1 — Sign Phase 0 baseline

**Branch:** `docs/coordinator-phase0-baseline-signed`
**Edits:** `docs/plans/option1-phase0-shared-contract-checklist.md`

### Procedure

1. Read the existing `docs/plans/option1-phase0-shared-contract-checklist.md` end-to-end.
2. Fill in §3 (Oracle baseline record) with concrete values:

   | Field | Value |
   |---|---|
   | Oracle repo path | `git@github.com:ArdeleanLucas/PARSE.git` |
   | Oracle branch | `main` |
   | Oracle commit SHA | `0951287a81` (verify with `git rev-parse origin/main` in the oracle clone before committing) |
   | Freeze date/time | 2026-04-26 (UTC offset of recording) |
   | Frontend validation evidence | output of `npm run typecheck && npm run test && npm run build` against oracle SHA, captured to `.hermes/reports/2026-04-26-oracle-frontend-gate.txt` and linked here |
   | Backend/API validation evidence | output of `pytest python/ -x` against oracle SHA, captured to `.hermes/reports/2026-04-26-oracle-backend-gate.txt` and linked here |
   | Fixture dataset version | the Saha01 corpus version currently used by `parse-mcp-speaker-import` skill (verify against existing skill's fixture references) |
   | Known accepted oracle quirks | enumerate at minimum: (a) torch interop-thread late-config tolerance landed in oracle PR #214, (b) ortho-repetition cascade fix in oracle PR #150, (c) compute subprocess + buffer-free checkpoints in oracle PR #152, (d) any others surfaced by the gate runs |

3. Tick every checkbox in §3 once the row is filled.
4. Fill in §2.1 (Required source set) — verify each listed file exists at the recorded oracle SHA, tick the boxes.
5. Fill in §2.2 (Precedence order) — record explicitly in the doc which precedence applies to which file class (architecture docs > stale planning, current oracle code > stale assumptions, coordinator decisions > lane-local convenience).
6. Add a closing §N — *"Both lanes acknowledge baseline"* — listing parse-builder and parse-back-end with date of acknowledgment fields left for those agents to fill on their next PR.

### Acceptance

- All checkboxes in §2.1, §2.2, §3 ticked
- Oracle SHA recorded matches `git rev-parse origin/main` in `/home/lucas/gh/ArdeleanLucas/PARSE` at the time of the PR
- Both gate-evidence files committed in `.hermes/reports/`
- PR title: `docs(coordinator): sign Phase 0 baseline for rebuild parity work`
- No code changes — docs and evidence files only

### Out-of-scope inside this PR

- Do not retroactively un-merge or re-litigate past PRs that were merged before Phase 0 was signed. Acknowledge that fact in a one-line note in the doc and move on.

---

## PR 2 — Publish progress scorecard

**Branch:** `docs/coordinator-progress-scorecard-2026-04-26`
**New file:** `docs/reports/2026-04-26-rebuild-progress-scorecard.md`

### Procedure

Use the `parse-rebuild-progress-scorecard` skill. Score on three independent axes — do not collapse them into a single number.

1. **Monolith reduction.** For each file in the plan's verified-monolith-pressure list (`server.py`, `chat_tools.py`, `ParseUI.tsx`, `mcp_adapter.py`, `provider.py`), record oracle LoC, rebuild LoC, delta, percentage, and a status of *untouched / in-progress / structurally-cracked / parity-complete*.
2. **Parity-evidence coverage.** For each P0 surface in `option1-parity-inventory.md` §5.1, record whether evidence has been recorded (yes/no) and where (file path or "none yet"). Most will be "none yet" at the time of this PR — that is the point.
3. **Desktop-distribution readiness.** For each item in `docs/desktop_product_architecture.md` (loopback, path rules, packaging, signing, update channel, etc.), record current state (not-started / scaffolded / wired / shipping). Most should be "not-started" — also the point.

Report sections (mandatory):

- Header: rebuild SHA, oracle SHA, date
- §1 Monolith reduction table
- §2 Parity-evidence coverage table
- §3 Desktop-distribution readiness table
- §4 Velocity (PRs merged in last 24h, broken down by type per the convention below)
- §5 Coordination flags (Phase 0 signed: yes/no; .hermes/state freshness; auto-lane activity)
- §6 Recommended next 3 priorities (NOT implementation — only re-rank what the coordinator should sequence next)

PR-type breakdown convention for §4: count `refactor:`, `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `other:`. A separate count of `docs: queue <agent> next task` (the queue-prompt subgenre) called out as such — these are the noise PR 4 will reduce.

### Acceptance

- File exists at `docs/reports/2026-04-26-rebuild-progress-scorecard.md`
- All six sections populated with concrete numbers (no TBDs)
- PR title: `docs(coordinator): publish 2026-04-26 rebuild progress scorecard`
- PR body summarizes the three top-level scores in 5 lines max

### Out-of-scope inside this PR

- Do not propose new tasks in the scorecard — that's coordinator's post-task action
- Do not score lanes individually as "good"/"bad" — score work, not agents

---

## PR 3 — Run a single P0 parity-evidence pass on Annotate

**Branch:** `docs/coordinator-parity-evidence-annotate-2026-04-26`
**New file:** `docs/reports/2026-04-26-annotate-parity-evidence.md`
**New evidence files (committed):** `.hermes/reports/parity/annotate/<flow>.{txt,png}` as needed

### Procedure

Use the `parse-rebuild-annotate-parity-audit` skill. The goal is to prove the parity loop *works*, not to run it against everything — so pick one P0 surface (Annotate) and one fixture speaker.

1. Boot the rebuild dev server against a copy of the Saha01 fixture workspace.
2. Boot the oracle dev server against the same fixture workspace.
3. For each of the following Annotate flows from `option1-parity-inventory.md` §5.1, exercise the same actions in both:
   - Speaker load: open the fixture speaker, verify intervals load identically
   - Save annotation: edit one interval's IPA, save, reload, verify persisted byte-equivalent
   - Mark concept done: mark, reload, verify badge state
   - STT request: trigger STT for one interval, verify job lifecycle and result identical (allow timing variance, not content variance)
   - Region capture: capture an offset anchor, verify offset detection result identical
   - Undo/redo: 3 edits + undo/redo, verify state matches at each step
   - Hotkey routing: verify play/pause, next/prev concept, save shortcuts work identically
4. Record evidence for each flow: a short text log + screenshot (if visual) committed under `.hermes/reports/parity/annotate/`.
5. The summary doc `docs/reports/2026-04-26-annotate-parity-evidence.md` lists each flow with PASS / FAIL / DEVIATION status, links to its evidence file, and a one-line note on any deviation.

If any flow shows a deviation, **do not fix it in this PR.** File a separate issue (or follow-up docs PR) and tag it for the appropriate implementation lane.

### Acceptance

- Summary doc exists with all 7 flows recorded
- Evidence files committed under `.hermes/reports/parity/annotate/`
- Status legend: PASS = byte-equivalent; DEVIATION = behavior differs but is acceptable per the inventory's "accepted oracle quirks"; FAIL = unintended behavior drift requiring follow-up
- PR title: `docs(coordinator): record Annotate parity evidence (Saha01 fixture)`
- PR body lists the 7 flows with status codes

### Out-of-scope inside this PR

- Compare, Tags, AI/chat parity — those are separate evidence passes for separate PRs.
- Fixing any deviations found.
- Touching `src/` or `python/`.

---

## PR 4 — Move task-queueing out of main-branch PRs

**Branch:** `docs/coordinator-handoff-convention`
**Edits:** `AGENTS.md`
**New files:**
- `.hermes/handoffs/README.md` (convention doc)
- `docs/reports/2026-04-26-historical-queue-prompt-prs.md` (audit-trail index)

### Why

Currently the convention is: when an autonomous lane finishes a task, the coordinator opens a `docs: queue <agent> next task — <slug>` PR with a markdown prompt under `docs/plans/`. That PR is then merged so the next autonomy run picks it up. This is noisy:

- Inflates the merged-PR count (~10 of 49 to date) without moving the rebuild forward
- Pollutes the changelog
- Couples coordinator workflow to PR-merge latency

Better convention: queue prompts live in `.hermes/handoffs/<agent>/<date>-<slug>.md` and are tracked, but task assignment does not require a PR to land on main.

### Procedure

1. Create `.hermes/handoffs/README.md` documenting:
   - Directory layout: `.hermes/handoffs/<agent-name>/<YYYY-MM-DD>-<slug>.md`
   - Lifecycle: `queued` (file exists) → `in-progress` (front-matter `status: in-progress`) → `done` (moved to `.hermes/handoffs/<agent>/done/`)
   - Front-matter format: `agent`, `queued_by`, `queued_at`, `status`, `related_prs` (list, optional)
   - Body format: same as today's `docs/plans/<agent>-next-task-*.md` files — context, scope, sequence, acceptance
2. Update `AGENTS.md` to point to the new convention and to deprecate the `docs: queue <agent> next task` PR pattern. Be explicit: *new* task queueing goes into `.hermes/handoffs/`; existing in-flight queue-prompt PRs (#36, #42, #48, #51, #53) finish their lifecycle under the old pattern.
3. Create `docs/reports/2026-04-26-historical-queue-prompt-prs.md` listing the 10 already-merged queue-prompt PRs by number, title, intended agent, and outcome (which implementation PR(s) followed). This preserves the audit trail that the new convention will keep in `.hermes/handoffs/<agent>/done/`.
4. As a one-time migration, move the *latest* queue prompt for each lane from `docs/plans/` into `.hermes/handoffs/<agent>/` to seed the new directory. Do not move historical ones.

### Acceptance

- `.hermes/handoffs/README.md` documents the convention
- `AGENTS.md` reflects the new convention and deprecates the old
- Audit-trail index file lists all 10 historical queue-prompt PRs
- Latest queue prompt per lane migrated as a seed
- PR title: `docs(coordinator): move task queueing from main-branch PRs to .hermes/handoffs/`

### Out-of-scope inside this PR

- Closing or retroactively reverting the historical queue-prompt PRs — they're merged history, leave them
- Force-closing in-flight queue-prompt PRs (#36, #42, #48, #51, #53) — let them finish under the old convention

---

## Sequencing notes

- **PR 1 (Phase 0 baseline) must land first.** PRs 2 and 3 reference the baseline SHAs and gate evidence committed by PR 1.
- PR 2 (scorecard) and PR 4 (handoff convention) can be opened in parallel after PR 1 lands.
- PR 3 (Annotate parity) is the most time-consuming because it requires running both servers — schedule it when fixture data is hot in cache.

---

## Conventions

- One commit per logical step (gate evidence capture, doc write, audit-trail index).
- PR title format: `docs(coordinator): <action>`
- Co-author line: `Co-Authored-By: parse-gpt <noreply@anthropic.com>`
- Do not merge your own PRs unless they are coordinator-only docs and another reviewer is unavailable. Even then, wait 24h for either implementation lane to flag concerns.
- Do not open implementation PRs from this lane.

---

## Skill references

Use these installed Hermes skills:

- `parse-rebuild-progress-scorecard` — methodology for PR 2
- `parse-rebuild-three-lane-pr-coordination` — coordination patterns generally; relevant for PR 4's handoff convention
- `parse-rebuild-health-audit` — the input format the scorecard consumes; run before PR 2
- `parse-rebuild-annotate-parity-audit` — methodology for PR 3
- `parse-stale-plan-replacement` — if PR 4 surfaces stale planning docs that should be archived alongside the queue-prompt cleanup
- `parse-mc-workflow` — file MC items for each of the 4 PRs

---

## What "done" looks like at the end of all 4 PRs

- Phase 0 baseline checklist signed with concrete oracle SHA, gate evidence, and acknowledged precedence
- Progress scorecard published with 6-section breakdown grounded in numbers
- Annotate P0 parity evidence recorded for one fixture speaker across 7 flows
- Task-queueing convention moved out of the main-branch PR stream into `.hermes/handoffs/`
- Coordinator can answer "is the rebuild on track?" with a published artifact rather than a verbal summary
- Auto-builder and auto-back-end lanes can resume against a signed baseline

---

## Out-of-band notes

- The currently-checked-out branch on `/home/lucas/gh/tarahassistant/PARSE-rebuild` is stale (`feat/parseui-shell-stage0-rebuild` is 4 commits behind main). Branch from `origin/main` directly.
- If running gate evidence reveals the oracle is currently red on any test, **record that fact in the Phase 0 doc** rather than picking a different SHA. The signed baseline reflects reality at the time of signing.
- The Annotate parity pass (PR 3) requires the dev server to run from the **canonical** PARSE clone (`/home/lucas/gh/ArdeleanLucas/PARSE`), not the lowercase duplicate (`/home/lucas/gh/ardeleanlucas/parse`). Both exist on disk; the lowercase one was running at 8766 as of 2026-04-26.
- This task does not include reviewing the open parse-builder and parse-back-end implementation PRs queued separately. That is the coordinator's *next* task after these 4 land.
