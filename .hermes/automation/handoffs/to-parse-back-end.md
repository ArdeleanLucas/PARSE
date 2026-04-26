# To parse-back-end

Status: queued_after_pr35

Current instruction:
- Lucas wants **longer tasks**, not more micro-PRs.
- Work from `.hermes/plans/2026-04-26-parse-back-end-next-task-clef-http-bundle.md`.
- After PR #35, build **one larger backend-only implementation PR** from current `origin/main` that extracts the remaining CLEF/contact-config HTTP cluster while preserving UI-facing contracts exactly.
- Keep this strictly backend-only and do not introduce any contract drift that would force visible UI change.
- Treat PR #35 as the immediate backend task and this new prompt as the queued follow-up behind it.

Grounded state:
- Current rebuild `origin/main`: `70f9783` — `refactor(config): extract config and CSV import HTTP handlers (#33)`
- Current queued parse-back-end handoff: PR #35 — tags/export bundle
- Builder lanes to avoid overlapping with:
  - PR #34 — frontend compare contract hardening
  - PR #36 — queued Builder UI parity bundle
- The next coherent inline backend cluster in `python/server.py` is:
  - `GET /api/contact-lexemes/coverage`
  - `GET /api/clef/config`
  - `POST /api/clef/config`
  - `POST /api/clef/form-selections`
  - `GET /api/clef/catalog`
  - `GET /api/clef/providers`
  - `GET /api/clef/sources-report`
