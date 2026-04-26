# To parse-builder

Status: ready_now

Current instruction:
- **Parity first.** The React PARSE UI must remain visually and behaviorally identical to the original workstation.
- **Do not re-imagine the UI.** No redesign, no modernization pass, no layout experimentation.
- Source of truth: `/home/lucas/gh/ardeleanlucas/parse` — especially `parse.html`, `compare.html`, `js/annotate/*`, `js/compare/*`, and the original labels / control ordering / panel structure.
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-cognate-controls-save-hardening.md`.
- Treat older queued Builder handoffs as superseded if they conflict with this parity-first instruction.

Grounded state:
- Current rebuild `origin/main`: `0d78bb8` — `test(compare): harden compute semantics regressions (#28)`
- Open implementation PRs `#27` and `#29` are narrow cleanup lanes; do **not** widen them into UI redesign. If parity corrections are needed, open a separate implementation PR from current `origin/main`.
- Lucas's hard rule: if anything in the React shell drifted from the original UI, correct it against the original before introducing further visual changes.
