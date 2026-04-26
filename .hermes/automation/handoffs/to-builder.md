# To parse-builder

Status: ready_now

Current instruction:
- Lucas wants **longer tasks**, not another tiny one-off PR.
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-compare-contract-bundle.md`.
- Build **one larger frontend-only implementation PR** from current `origin/main` that consolidates the remaining compare-side contract/persistence cleanup while keeping the React UI identical to the original PARSE workstation.
- Treat the original UI at `/home/lucas/gh/ardeleanlucas/parse` as the visual/interaction spec.
- Audit open frontend implementation PRs `#27`, `#29`, and `#31`; absorb or supersede their safe remaining deltas as appropriate instead of spawning another micro-PR chain.
- If any of those PRs are already effectively landed or obsolete by the time you start, note that explicitly and continue with the remaining delta.
- Do **not** redesign or re-imagine the UI.

Grounded state:
- Current rebuild `origin/main`: `0d78bb8` — `test(compare): harden compute semantics regressions (#28)`
- Open frontend implementation PRs visible right now:
  - PR #27 — `fix(compare): use typed CLEF client in BorrowingPanel`
  - PR #29 — `fix(config): wire configStore update to typed client`
  - PR #31 — `fix(compare): harden CognateControls save failures`
- Backend lane remains on PR #23 and should stay non-overlapping.
