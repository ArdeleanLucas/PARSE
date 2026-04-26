# To parse-builder

Status: ready_now

Current instruction:
- Lucas wants **longer tasks**, not more micro-PRs.
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-ui-parity-bundle.md`.
- Build **one larger frontend-only implementation PR** from current `origin/main` that audits and corrects the remaining shell / chrome UI parity drift against the oracle/live PARSE UI.
- Use `/home/lucas/gh/ardeleanlucas/parse` as the canonical UI reference.
- **Do not redesign or re-imagine the UI.**
- Stay strictly out of the compare contract files already bundled in PR #34.
- Treat merged PR #38 as done; this next task should continue the remaining shell-parity work beyond that compare-compute copy removal.

Grounded state:
- Current rebuild `origin/main`: `72ae7ef` — `fix(ui): remove rebuild-only compare semantics copy (#38)`
- Open Builder implementation PR still in flight but non-overlapping:
  - PR #34 — `fix(compare): bundle frontend contract hardening`
- Open parse-back-end lanes to avoid overlapping with:
  - PR #39 — `refactor(tags): extract tag and export HTTP handlers`
  - PR #37 — `docs: add parse-back-end CLEF HTTP bundle handoff`
- This task should focus on shell/UI parity surfaces such as `src/ParseUI.tsx`, `src/components/parse/ConceptSidebar.tsx`, `src/components/parse/RightPanel.tsx`, and their tests.
