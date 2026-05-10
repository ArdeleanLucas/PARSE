# Coordinate the compute-child stdout-fence repair across two backend lanes

**Date:** 2026-05-10
**Agent:** parse-coordinator
**Branch:** `docs/restore-compute-child-stdout-coord` off origin/main
**Coordinated lanes:**
- **Lane A** (already drafted, assumed dispatched): `.hermes/handoffs/parse-back-end/2026-05-10-restore-rerun-child-stdout.md` — branch `fix/lexeme-rerun-child-stdout-tee`. Narrow fix to `python/server_routes/lexeme_rerun.py:_lexeme_rerun_subprocess_entry`.
- **Lane B** (this coordinator drafts and dispatches it): branch `fix/tee-compute-subprocess-stderr`. Broader fix introducing `python/shared/subprocess_tee.py` with `install_child_tee(log_path)` helper, then wiring it into `python/server_routes/jobs.py::_compute_subprocess_entry` and `python/workers/compute_worker.py::worker_main`.

---

## Background

A read-only audit on 2026-05-10 (Explore subagent against `/tmp/parse-runtime/` HEAD `0c79e82`) found three instances of the same regression class introduced by PR #334 ("fix(lexeme): fence rerun IPA and ORTH subprocesses", commit `5bc9828`): a `multiprocessing.spawn` child entry function that replaces `sys.stderr` with a per-PID log file and never tees back to the inherited fd 2. Together with PR #338 ("track tagged lexeme reruns as compute jobs", commit `0c79e82`) that wrapped the rerun-by-tag path in a polled compute job, the parent terminal lost almost every live `[ORTH]`/`[IPA]`/`[STT]` / `[WORKER] dispatching ...` line that previously surfaced — leaving only the FE polling wallpaper for `/api/compute/lexemes_rerun_by_tag/status`.

The audit identified three sites; all three need the same fix shape (dup fd 2 BEFORE the rebind, swap to a write-side tee, keep `faulthandler.enable` pointed at the file fd only):

1. `python/server_routes/lexeme_rerun.py:_lexeme_rerun_subprocess_entry` — **lane A** (narrow, in-file Tee class).
2. `python/server_routes/jobs.py:_compute_subprocess_entry` — **lane B** (uses shared helper).
3. `python/workers/compute_worker.py:worker_main` — **lane B** (uses shared helper).

Lane A was drafted first because the symptom Lucas pasted in chat was specifically the rerun-by-tag path. Lane B is broader and covers the wider regression surface. Either lane can land first.

### Confirmed clean by the same audit (do NOT re-flag in any handoff)

- `python/server_routes/annotate.py:_full_pipeline_ipa_subprocess_entry` (~line 2546) — no rebind, only checkpoint log.
- `python/ai/tools/artifact_tools.py:205` — properly restores `sys.stderr` in `finally`.
- All `subprocess.run(..., capture_output=True)` callers in `video_sync.py`, `normalize_audio.py`, `peaks.py`, `media.py`, `batch_reextract.py`, `video_clip_extract.py`, `speaker_locks.py` — short-lived externals (ffmpeg/ffprobe), not long-running compute children.

---

## Coordinator scope

Four responsibilities, in order:

### 1. Draft and dispatch lane B

This coordinator authors the lane B handoff itself. File it at `.hermes/handoffs/parse-back-end/2026-05-10-tee-compute-subprocess-stderr.md` (no kickoff file — Lucas's standing rule as of 2026-05-10 is one .md per task; the initial prompt is provided in chat or directly in the agent invocation, never as a paired file). Then dispatch a fresh parse-back-end agent against it.

The lane B handoff body must cover:

- **Branch:** `fix/tee-compute-subprocess-stderr` off origin/main, fresh worktree under `/home/lucas/gh/worktrees/`.
- **Companion lane note:** lane A may merge before, after, or alongside; coordination handled below.
- **Hit 1 — `python/server_routes/jobs.py:_compute_subprocess_entry` (~lines 320‑400):** spawned at ~line 274 in `_launch_compute_subprocess` via `multiprocessing.get_context("spawn")`. Today does:
  ```python
  try:
      child_stderr = open('/tmp/parse-compute-{0}.stderr.log'.format(job_id), 'w', encoding='utf-8')
      _server.sys.stderr = child_stderr
  except Exception:
      pass
  ```
  Affects every compute type that goes through subprocess dispatch (ortho, ipa, full_pipeline, forced_align, boundaries, STT, retranscribe, offset_detect, training, lexemes_rerun_by_tag).
- **Hit 2 — `python/workers/compute_worker.py:worker_main` (~lines 452‑560):** persistent worker spawned at line 98 via `multiprocessing.get_context("spawn")` at line 74. Same `sys.stderr = open("/tmp/parse-compute-worker.stderr.log", "w", ...)` rebind without tee. Swallows `[WORKER] starting / dispatching / completed` lifecycle and everything dispatched through the persistent worker.
- **Shared helper at `python/shared/subprocess_tee.py`** (new file; create `python/shared/__init__.py` if the package doesn't exist — grep first):
  ```python
  """Tee helper for multiprocessing.spawn child entry functions."""
  from __future__ import annotations
  import faulthandler, os, sys
  from typing import Any, IO, Tuple

  class _Tee:
      def __init__(self, *streams: Any) -> None:
          self._streams = tuple(streams)
      def write(self, data: str) -> int:
          n = 0
          for s in self._streams:
              try:
                  n = s.write(data); s.flush()
              except Exception:
                  pass
          return n or len(data)
      def flush(self) -> None:
          for s in self._streams:
              try:
                  s.flush()
              except Exception:
                  pass
      def isatty(self) -> bool:
          return False
      def fileno(self) -> int:  # pragma: no cover
          raise OSError("Tee has no single fileno")

  def install_child_tee(log_path: str) -> Tuple[IO[str], IO[str], IO[str]]:
      """Open log_path and rebind sys.stdout/stderr to tee both there and to
      the parent's inherited fd 1/2. Enable faulthandler against the file fd."""
      log_fh = open(log_path, "w", buffering=1, encoding="utf-8")
      inherited_out = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8", errors="replace")
      inherited_err = os.fdopen(os.dup(2), "w", buffering=1, encoding="utf-8", errors="replace")
      sys.stdout = _Tee(log_fh, inherited_out)
      sys.stderr = _Tee(log_fh, inherited_err)
      faulthandler.enable(file=log_fh, all_threads=True)
      return log_fh, inherited_out, inherited_err
  ```
- **Wire-in in both files:** replace the `try: ... open(...); sys.stderr = ...; except: pass` block with `try: install_child_tee(<log_path>); except Exception: pass`. Preserve the surrounding fall-through so log-open failure does not crash the child.
- **Coordination note (this coordinator chooses one based on lane A's state at dispatch time):**
  - If lane A still open: "Lane A still open (PR #X branch fix/lexeme-rerun-child-stdout-tee). Leave a TODO comment in lexeme_rerun.py pointing at python/shared/subprocess_tee.py — do not edit lexeme_rerun.py content. Coordinator will dedupe in a follow-up."
  - If lane A merged: "Lane A merged at SHA $SHA. Rebase onto origin/main, then refactor lexeme_rerun.py to import install_child_tee from python/shared/subprocess_tee.py and delete the local _LexemeRerunTee class. Update python/server_routes/test_lexeme_rerun_subprocess_isolation.py imports."
- **Tests** (new files, all mock heavy work):
  - `python/shared/test_subprocess_tee.py`: pipe-capture parent fd 2 around `install_child_tee`, write via `print(..., file=sys.stderr)`, assert both captured fd 2 bytes AND log file contain the line. Same for fd 1. Closed-stream-doesn't-crash test on `_Tee`. Unwritable-log-path test (caller's `except Exception: pass` is the contract; helper itself raises).
  - `python/server_routes/test_jobs_compute_subprocess_tee.py`: real `multiprocessing.get_context("spawn")` of `_compute_subprocess_entry` with a stub compute that prints `[ORTH] hello` to stderr; pipe-capture parent fd 2; assert it contains `[ORTH] hello` AND `/tmp/parse-compute-<job_id>.stderr.log` is populated.
  - `python/workers/test_compute_worker_tee.py`: real spawn of `worker_main` with a fake job queue that submits one no-op job whose stub prints `[WORKER] dispatching job_id=test`; pipe-capture parent fd 2; assert the line surfaces.
- **Validation:** BLOCK_LIVE_PROCESS_ISOLATION; standard 4 gates; isolated smoke on `PARSE_PORT=18766` against `/tmp/parse-isolation-tee-compute-stderr/` (NEVER `/home/lucas/parse-workspace`); seed 1 speaker × 2 concept windows; POST `/api/compute/ortho` then `/api/compute/ipa`; capture parent stderr to a file; assert it contains live `[ORTH]`/`[IPA]` AND `concept-window` lines emitted DURING the job (not just post-completion summary); assert `/tmp/parse-compute-{job_id}.stderr.log` AND `/tmp/parse-compute-worker.stderr.log` are also populated (proves tee, not replacement); `/api/config` stays 200 throughout. Mock providers in unit tests; no real wav2vec2 or HF Whisper inference.
- **Reply format:** PR URL on `ArdeleanLucas/PARSE`, ≤6 bullets, list of files modified with line ranges, two pasted live-log lines from the smoke capture (compute-subprocess + persistent-worker), tail of validation output, coordination note about whether lane A was rebased or TODO-only. Refetch before reporting `mergeStateStatus`. Do NOT merge.

The two lanes touch disjoint files (modulo lane B's optional TODO comment in `lexeme_rerun.py`). They CAN run in parallel.

### 2. Watch both lanes through merge

For each lane PR, after Lucas merges:

- `git fetch origin --quiet --prune`
- Capture: PR #, merge SHA, fresh CI gate status (4 gates), `mergeStateStatus`.
- Confirm the canonical clone at `/home/lucas/gh/tarahassistant/PARSE-rebuild/` is back on main (`git checkout main && git pull --ff-only origin main`) and the lane worktree is removed (`git worktree remove -f <path>`).

Coordinator does NOT merge — Lucas merges. Coordinator does NOT push to either lane's branch. Read-only on lane branches.

### 3. Post-merge dedupe (only if both lanes shipped a duplicate Tee class)

If lane A landed first with an in-file `_LexemeRerunTee` class AND lane B landed second without rebasing it onto `python/shared/subprocess_tee.py`, draft a small follow-up backend handoff at `.hermes/handoffs/parse-back-end/2026-05-1X-consolidate-subprocess-tee.md` queuing the dedupe (no kickoff file). Brief and specific: "Delete `_LexemeRerunTee` from `python/server_routes/lexeme_rerun.py`. Replace its single use site with `install_child_tee` from `python/shared/subprocess_tee.py`. Update `python/server_routes/test_lexeme_rerun_subprocess_isolation.py` to import the shared Tee class. One PR, ≤30 LoC delta." Mark the path as superseded in lane A's original handoff if the dedupe is queued.

If lane B rebased correctly OR landed first, this step is a no-op. Document that in the reply.

### 4. AGENTS.md note + audit summary docs PR

This lane's deliverable. Single PR on branch `docs/restore-compute-child-stdout-coord`:

- Add a new section to `AGENTS.md` titled "Compute children must tee stderr, not redirect" (≤15 lines):
  - Pattern: any `multiprocessing.get_context("spawn")` child entry that opens a per-PID logfile MUST use `install_child_tee(log_path)` from `python/shared/subprocess_tee.py`.
  - Why: replacing `sys.stderr` (rather than teeing) silently swallows live progress that the parent terminal previously surfaced — see PR #334 followup audit on 2026-05-10.
  - When a per-PID log file is needed at all: only when the parent does an OOM/segfault tail-into-JSON capture (e.g. `_read_child_log_tail`). For pure progress-streaming children, prefer the inherited fd 2 directly without a logfile.
  - Cross-link both lane PRs.
- Add `docs/architecture/compute-subprocess-stdio.md` (or extend an existing compute-job doc — search `docs/` first):
  - Diagram of the spawn → tee → parent-fd-2 path.
  - Inventory of the three child entries (lexeme_rerun, _compute_subprocess_entry, worker_main) with file:line refs.
  - Inventory of confirmed-clean spawn paths (`_full_pipeline_ipa_subprocess_entry`, `artifact_tools.py:205`) with one-line "why clean" notes so future audits don't re-flag them.
  - Date-stamp the audit run that produced this work.
- Add `docs/dogfood/2026-05-10-restore-compute-child-stdout.md`: manual checklist Lucas can run against the live runtime (start parse-run, trigger a tagged rerun, confirm `[ORTH] concept-window i/N concept='…' → 'text'` lines appear in the parent terminal during the job). Coordinator authors but does NOT run.
- Move both lane handoffs to `.hermes/handoffs/parse-back-end/done/`. Move this coordinator handoff to `.hermes/handoffs/parse-coordinator/done/` as the last commit before opening the docs PR.

### Out of scope

- Implementation work in either lane (BE handles).
- Modifying lane PRs directly (read-only on lane branches).
- parse-run, browser tools, screenshots — banned for agents.
- Rewriting any clean spawn entry that the audit cleared.
- Writing kickoff.md files anywhere — Lucas's standing rule (2026-05-10): one .md per task, no paired-file kickoffs.

---

## Validation

Pre-PR audit checklist (MUST pass before opening the docs PR):

- Both lane PRs merged to main with green CI on all gates.
- `git fetch origin --quiet --prune && git log origin/main --oneline -10` shows both merge commits.
- Grep audit clean: `grep -rn 'sys\.stderr *= *open' python/ | grep -v test_ | grep -v shared/subprocess_tee.py` returns nothing (only the new shared helper should match the pattern, and only on its docstring/example).
- Quote one live `[ORTH]`/`[IPA]` line from lane A's smoke capture and one `[WORKER]` line from lane B's smoke capture (proves both tees work end-to-end).

Standard validation for the docs PR itself:

```bash
npm run test --silent
PYTHONPATH=python python -m pytest python/ -x -q
npm run typecheck
npm run build
```

(All four should be no-ops since only docs change, but run them.)

HARD BAN: no parse-run, no browser, no screenshots. Coordinator audits via `git log` + `grep` + read-only file inspection only.

Post-merge canonical-clone hygiene:

```bash
cd /home/lucas/gh/tarahassistant/PARSE-rebuild
git fetch origin --quiet --prune
if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then
  git checkout main && git pull --ff-only origin main
fi
git worktree remove -f /home/lucas/gh/worktrees/restore-compute-child-stdout-coord
git branch -D docs/restore-compute-child-stdout-coord 2>/dev/null || true
git status --short --branch  # must show `## main...origin/main`
```

`git fetch origin --quiet --prune` before reporting `mergeStateStatus`. Docs PR must be on `ArdeleanLucas/PARSE`. Do NOT merge.

---

## Reply format

Multi-step reply, one update per milestone:

1. **Lane B handoff drafted** — path to `.hermes/handoffs/parse-back-end/2026-05-10-tee-compute-subprocess-stderr.md` and confirmation that no kickoff file was created.
2. **Lane B dispatched** — coordination note included (rebase-vs-TODO based on lane A's state at dispatch time).
3. **Lane A status** — PR #, merge SHA, CI gates green, `mergeStateStatus`, one pasted smoke line.
4. **Lane B status** — PR #, merge SHA, CI gates green, `mergeStateStatus`, two pasted smoke lines (compute-subprocess + persistent-worker).
5. **Dedupe decision** — either "no-op, lane B rebased correctly" or PR # of the consolidation follow-up handoff.
6. **Audit grep result** — pasted output of the `grep -rn 'sys\.stderr *= *open' python/` check.
7. **Docs PR** — PR # + URL (must contain `ArdeleanLucas/PARSE`) + commit SHA + confirmed `baseRefName=main` + 4 CI gate statuses + fresh `mergeStateStatus` + canonical-clone-on-main confirmation + pointer to `docs/dogfood/2026-05-10-restore-compute-child-stdout.md`.
