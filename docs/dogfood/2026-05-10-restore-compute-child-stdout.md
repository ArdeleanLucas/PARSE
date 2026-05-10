# Dogfood checklist — restore live compute child stdout/stderr

**Date:** 2026-05-10  
**Coordinator:** parse-coordinator  
**Backend PRs:** #339, #340  
**Run owner:** Lucas / local runtime operator

Coordinator did **not** run this checklist. It is a manual live-runtime verification recipe for Lucas after the backend merges.

## Preconditions

- Current PARSE checkout includes PR #339 and PR #340.
- The backend starts normally with Lucas's usual `parse-run` flow.
- Use a disposable/safe workspace or a known test speaker/tag if mutating annotations.

## Tagged lexeme rerun check

1. Start PARSE with the normal `parse-run` terminal visible.
2. In the UI, choose a speaker with at least one tagged concept window.
3. Trigger the tagged-only rerun path.
4. While the job is running, watch the parent terminal, not just `/tmp` logs.
5. Confirm at least one live line like this appears during the job:

```text
[ORTH] concept-window i/N concept='…' → '…'
```

Acceptable variants include `[IPA] ...`, `[STT] ...`, or provider/model-load progress lines, as long as they surface in the parent terminal while the job is active.

## General compute subprocess check

1. Trigger a normal compute job that uses the subprocess runner (`/api/compute/ortho`, `/api/compute/ipa`, or full-pipeline concept windows).
2. Confirm the parent terminal shows live model/progress output during the job, not only after completion.
3. Confirm the compute job still completes and the UI progress header continues to poll normally.

## Persistent worker check

1. Trigger a path that uses the persistent worker, if enabled in the local runtime mode.
2. Confirm worker lifecycle output appears in the parent terminal, for example:

```text
[WORKER] dispatching job_id=...
```

3. Confirm `/tmp/parse-compute-worker.stderr.log` is still populated for post-mortem diagnostics.

## Pass criteria

- Parent terminal shows live `[ORTH]`/`[IPA]`/`[STT]` concept-window or provider progress during compute work.
- Parent terminal shows live `[WORKER]` lifecycle lines when the persistent worker path is active.
- Per-child log files still exist/populate for diagnostics.
- No browser screenshots are needed for this verification.

## Fail criteria

- Parent terminal shows only HTTP polling lines while compute work runs.
- Live progress appears only in `/tmp/parse-compute-*.stderr.log` but not in the terminal.
- A crash no longer leaves a useful per-child log tail.
