# To parse-back-end

Status: ready_now

Current instruction:
- Stay **strictly backend-only**.
- Support the original-UI parity rule by preserving API behavior exactly; do not propose or drive UI redesign.
- Work from `.hermes/plans/2026-04-26-parse-back-end-next-task-config-import-http-slice.md`.
- Open a fresh implementation PR from current `origin/main`; do not resume stale auth/job-observability lanes.

Grounded state:
- Current rebuild `origin/main`: `0d78bb8` — `test(compare): harden compute semantics regressions (#28)`
- Builder is being redirected to an original-UI parity audit/correction pass. Your lane should remain backend-only and avoid frontend/UI surfaces.
- Lucas's hard rule: the React UI must match the original workstation exactly; backend work must not introduce contract drift that forces visible UI changes.
