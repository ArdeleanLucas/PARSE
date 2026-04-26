# To parse-back-end

Status: queued_after_pr33

Current instruction:
- Lucas wants **longer tasks**, not another tiny backend slice.
- Work from `.hermes/plans/2026-04-26-parse-back-end-next-task-tags-export-http-bundle.md`.
- Build **one larger backend-only implementation PR** from current `origin/main` that extracts the remaining tag + export HTTP cluster while preserving UI-facing contracts exactly.
- Treat merged PR #33 as done; this is the next backend bundle after config/import extraction landed on `main`.
- Stay strictly outside frontend/UI surfaces and do not introduce any contract drift that would force visible UI change.

Grounded state:
- Current rebuild `origin/main`: `70f9783` — `refactor(config): extract config and CSV import HTTP handlers (#33)`
- Builder is on a separate frontend-only bundle via PR #32.
- The remaining adjacent inline backend cluster in `python/server.py` includes:
  - `GET /api/tags`
  - `POST /api/tags/merge`
  - `GET /api/export/lingpy`
  - `GET /api/export/nexus`
