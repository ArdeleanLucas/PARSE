# To parse-builder

Status: queued_after_pr34

Current instruction:
- Lucas wants **longer tasks**, not more micro-PRs.
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-ui-parity-bundle.md`.
- After PR #34, build **one larger frontend-only implementation PR** that audits and corrects any React UI drift against the oracle/live PARSE UI.
- Use `/home/lucas/gh/ardeleanlucas/parse` as the canonical UI reference.
- Do **not** redesign or re-imagine the UI.
- Keep this lane strictly frontend-only and non-overlapping with parse-back-end PR #35.

Grounded state:
- Current rebuild `origin/main`: `70f9783` — `refactor(config): extract config and CSV import HTTP handlers (#33)`
- Active Builder implementation PR: #34 — `fix(compare): bundle frontend contract hardening`
- Queued parse-back-end handoff PR: #35 — `docs: add parse-back-end tags/export bundle handoff`
- Earlier Builder docs PR #32 has been consumed by PR #34 and should no longer be treated as the next task source.
