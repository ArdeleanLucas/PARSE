# To parse-builder

Status: pending

Current instruction:
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-compute-mode-semantics-audit.md`.
- Open a fresh implementation PR from current `origin/main`; do not reuse the old crash-fix or decisions branches.
- Keep the slice frontend/shared-shell focused. If you find a real backend contract gap, stop at the boundary and report the exact follow-up instead of widening into `python/server.py` casually.

Grounded state:
- Current rebuild `origin/main`: `7b33696` — `fix(annotate): prevent TranscriptionLanes hook-order crash (#19)`
- Open PRs: none
- Prior PR #14 / #19 blockers are resolved on main
- Next builder-visible slice: `docs/plans/parseui-current-state-plan.md §5` compute-mode semantics / payload audit
