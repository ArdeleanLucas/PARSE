# To parse-back-end

Status: ready_now

Current instruction:
- Stay **strictly backend-only**.
- While Builder audits the React UI against the original workstation, your job is to preserve backend contracts so the UI does not need to change.
- Work from `.hermes/plans/2026-04-26-parse-back-end-next-task-config-import-http-slice.md`.
- Before changing code, verify the current request/response behavior of the config/import routes you touch.
- If you discover any contract drift that would require visible UI change, stop and report it instead of changing the UI.

Grounded state:
- Current rebuild `origin/main`: `0d78bb8` — `test(compare): harden compute semantics regressions (#28)`
- Builder is being explicitly redirected to an original-UI parity audit/correction pass.
- Lucas hard rule: the React UI must match the original PARSE workstation exactly; backend work must not force UI redesign.
