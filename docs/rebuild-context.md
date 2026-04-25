# PARSE rebuild repo context

**Repo:** `TarahAssistant/PARSE-rebuild`
**Created:** 2026-04-25
**Purpose:** isolate refactor/rebuild work from the live thesis repo.

## Oracle relationship

- **Live/oracle repo:** `ArdeleanLucas/PARSE`
- **Local oracle path:** `/home/lucas/gh/ardeleanlucas/parse`
- **Rebuild repo local path:** `/home/lucas/gh/tarahassistant/PARSE-rebuild`
- Until Lucas explicitly signs off on parity, the oracle repo remains the behavior source of truth for:
  - UI behavior
  - API contracts
  - background job semantics
  - annotation/enrichment storage invariants
  - LingPy/NEXUS export expectations

## Initial import point

This rebuild repo was seeded from oracle `origin/main` at:

- commit `e3843ab1965713dfc9d4cceb1a061c3430c963c6`
- includes refactor-associated PRs:
  - `#225` docs: add current-state ParseUI shell refactor plan
  - `#226` refactor: extract server static and workspace config helpers

## Policy

1. **Future refactor PRs land here first.**
2. **The live/oracle repo should stay stable.** If refactor work accidentally lands there, undo it with a narrow revert/sync PR.
3. **Parity must stay explicit.** Record deltas under `parity/` and `parity/deviations.md` rather than relying on memory.
4. **Do not treat this repo as production/runtime truth** until Lucas explicitly promotes it.

## Immediate next steps

- Freeze Phase 0 shared contracts and parity fixtures.
- Continue frontend shell refactor and backend modularization here.
- Mirror only deliberate, low-risk live bugfixes from the oracle when needed.
