# To parse-back-end

Status: ready_now

Current instruction:
- **Correction:** PR #39 is complete and merged; do not treat PR #35 as the active next-task reference anymore.
- Lucas wants **longer tasks**, not more micro-PRs.
- Work from `.hermes/plans/2026-04-26-parse-back-end-next-task-clef-http-bundle.md`.
- Build **one larger backend-only implementation PR** from current `origin/main` that extracts the remaining CLEF/contact-config HTTP cluster while preserving UI-facing contracts exactly.
- Keep this strictly backend-only and do not introduce any contract drift that would force visible UI change.

Grounded state:
- Current rebuild `origin/main`: `bd226e1` — `refactor(tags): extract tag and export HTTP handlers (#39)`
- Recently landed backend slice: PR #39 — tags/export handlers extracted
- Open frontend lanes to avoid overlapping with:
  - PR #34 — compare contract hardening
  - PR #36 — queued Builder annotate parity bundle
- The next coherent inline backend cluster in `python/server.py` is:
  - `GET /api/contact-lexemes/coverage`
  - `GET /api/clef/config`
  - `POST /api/clef/config`
  - `POST /api/clef/form-selections`
  - `GET /api/clef/catalog`
  - `GET /api/clef/providers`
  - `GET /api/clef/sources-report`
