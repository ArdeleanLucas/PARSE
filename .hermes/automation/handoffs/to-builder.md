# To parse-builder

Status: ready_now

Current instruction:
- **Correction:** do not reuse the previous shell-parity framing as-is. PR #38 already consumed that visible compare-controls parity slice.
- Lucas wants a **genuinely new longer task**, not the stale version of PR #36.
- Work from `.hermes/plans/2026-04-26-parse-builder-next-task-annotate-parity-bundle.md`.
- Build **one larger frontend-only implementation PR** from current `origin/main` that audits and corrects the remaining **annotate-mode workstation parity** against the oracle/live PARSE UI.
- Use `/home/lucas/gh/ardeleanlucas/parse` as the canonical UI reference.
- **Do not redesign or re-imagine the UI.**
- Stay strictly out of the compare-contract files already bundled in PR #34 and out of backend-owned surfaces.

Grounded state:
- Current rebuild `origin/main`: `bd226e1` — `refactor(tags): extract tag and export HTTP handlers (#39)`
- Recently landed UI parity slice: PR #38 — compare compute explainer removal
- Open non-overlap lanes:
  - PR #34 — compare contract hardening
  - PR #37 — queued parse-back-end CLEF HTTP bundle
- This next Builder task should focus on annotate-mode parity surfaces such as `src/components/annotate/*`, relevant `src/ParseUI.tsx` annotate sections, and their tests.
