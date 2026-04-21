# docs/archive/

Archived 2026-04-20 per [`../DOCS_AUDIT_2026-04-20.md`](../DOCS_AUDIT_2026-04-20.md).

These documents describe **landed work, completed cleanups, or the pre-React vanilla-JS architecture**. They are preserved here for historical reference. Do not use them as active plans — they no longer reflect the current codebase.

## Contents

### Top-level
- [`BUILD_SESSION.md`](BUILD_SESSION.md) — Wave-based build plan for vanilla-JS modules (v4.0 Waves 5–9). Superseded by the React rewrite.

### plans/
- `MC-300-parseui-recovery.md` — ParseUI Priority 1 wiring recovery; all tasks landed.
- `MC-301-parseui-actions-import.md` — Actions menu Import Speaker modal; landed PR #18.
- `MC-305-branch-cleanup-findings-pr.md` — Branch cleanup docs PR task; complete.
- `MC-306-parseui-current-state-plan.md` — Meta-task to create the current-state plan; complete.
- `actions-job-lifecycle-pr.md` — `useActionJob` hook spec; landed PR #38.
- `compare-branch-audit.md` — One-time `feat/compare-react` branch audit; decision acted on.
- `github-branch-cleanup-findings-2026-04-10.md` — Branch cleanup snapshot 2026-04-10; all pruned.
- `mc-308-audio-pipeline-fix.md` — Audio pipeline fix; landed PR #43.
- `parseui-wiring-todo.md` — Vanilla-JS-era wiring TODO; superseded by `plans/parseui-current-state-plan.md`.
- `pr38-dispatch-specs.md` — TypeScript dispatch specs for PR #38; landed.
- `pr38-role-split.md` — Agent handoff coordination for PR #38; landed.
- `repo-cleanup-preflight.md` — 2026-04-09 branch snapshot; branches pruned.

### plans/oda/
The Oda agent persona owned Track B (Compare Mode) of the dual-agent React+Vite pivot. Every component it scoped is now in `src/components/compare/` and `src/hooks/`. `b6-speaker-import.md` remains in `docs/plans/oda/` only as a historical handoff note that now points readers to the landed React component; the rest of the Oda briefs live here as archive material.

- `b1-concept-table.md` through `b5-enrichments-panel.md` — Component specs; all landed.
- `b7-export.md` — `useExport` hook spec; landed.
- `b8-compute-job.md` — `useComputeJob` hook spec; landed.
- `b9-compare-mode.md` — CompareMode assembly; landed.
- `coordination.md` — Oda↔ParseBuilder protocol; Track B audit closed 2026-04-08.
- `oda-core.md` — Oda identity and ownership map; historical.
- `phase-0.md` — Scaffold gate; long passed.
