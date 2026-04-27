> **Historical (post-cutover 2026-04-27).** Preserved as cutover-narrative reference. Active state lives in [main docs/](../..).

# ParseBuilder — Personal TODO

> **Updated:** 2026-04-20 — trimmed to a minimal pointer. The historic completion log
> was moved out; active execution tracking lives in `parseui-current-state-plan.md`.

**Owner:** ParseBuilder (@parse-builder)
**Domain:** Annotate mode + shared platform (waveform, spectrogram, phonetic tools)

## Authoritative sources

1. `AGENTS.md` — branch policy, deferred-validation policy, contract table
2. `docs/plans/parseui-current-state-plan.md` — live execution plan for ParseUI work
3. `docs/plans/deferred-validation-backlog.md` — MC-299 and other deferred tests

## Currently blocked or in-flight

- None blocking — work any stage Lucas asks for. Keep C5 (LingPy TSV browser verification)
  and C6 (full Annotate/Compare regression) on the deferred list in
  `deferred-validation-backlog.md` rather than as gates.

## PR workflow

- Branch from `origin/main` → push → `gh pr create --base main --reviewer TrueNorth49`.
- Never merge yourself. Lucas merges.
- Never push directly to main.
