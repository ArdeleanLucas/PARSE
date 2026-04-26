# To parse-builder

Status: ready_now

Current instruction:
- **Before any more frontend work, audit the current React UI against the original PARSE UI.**
- **No UI re-imagining is allowed.** The React workstation must stay visually and behaviorally identical to the original.
- Use `/home/lucas/gh/ardeleanlucas/parse` as the source of truth.
- Check at minimum:
  - `parse.html`
  - `compare.html`
  - `js/annotate/*`
  - `js/compare/*`
- Specifically inspect current frontend work, including PR #27 and PR #29, for any visible/layout/interaction drift from the original.
- If drift exists, fix it in a fresh implementation PR from current `origin/main`.
- If PR #27 or PR #29 are clean and purely under-the-hood, say so explicitly in your report.
- Do **not** widen this into redesign or modernization.

Grounded state:
- Current rebuild `origin/main`: `0d78bb8` — `test(compare): harden compute semantics regressions (#28)`
- Current frontend implementation PRs visible in the queue:
  - PR #27 — `fix(compare): use typed CLEF client in BorrowingPanel`
  - PR #29 — `fix(config): wire configStore update to typed client`
- Lucas hard rule: original UI parity is the spec.
