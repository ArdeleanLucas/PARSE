# To parse-builder

Status: pending

Current instruction:
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-borrowing-panel-typed-client.md`.
- Open a fresh implementation PR from current `origin/main`.
- Keep this slice frontend-only and stay out of parse-back-end PR #23: https://github.com/TarahAssistant/PARSE-rebuild/pull/23

Grounded state:
- Current rebuild `origin/main`: `5cf12ca` — `feat(compare): make compute payload semantics explicit (#24)`
- Recommended Builder slice: replace the remaining raw `fetch("/config/sil_contact_languages.json")` in `src/components/compare/BorrowingPanel.tsx` with the existing typed CLEF client surface and update its tests accordingly.
