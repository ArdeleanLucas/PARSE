# To parse-back-end

Status: pending

Current instruction:
- Work from `.hermes/plans/2026-04-26-parse-back-end-next-task-config-import-http-slice.md`.
- Open a fresh implementation PR from current `origin/main`; do not resume any old auth/job-observability lane.
- Stay strictly outside the Builder compute-mode semantics audit preserved by merged PR #22: https://github.com/TarahAssistant/PARSE-rebuild/pull/22

Grounded state:
- Current rebuild `origin/main`: `10de7f4` — `docs: add parse-builder compute-mode audit handoff (#22)`
- Open PR set should only include this parse-back-end handoff PR once it is opened
- Recommended backend slice: extract `/api/config`, `/api/concepts/import`, and `/api/tags/import` handlers from `python/server.py` into a dedicated `python/app/http` helper module with direct app-layer tests plus thin server-wrapper regressions
