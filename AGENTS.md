# AGENTS.md — PARSE React + Vite Integration (2026)

## Current State (updated 2026-04-08)

PARSE has already crossed the React pivot integration point on **`feat/parse-react-vite`**.

- **Phase C1–C4 complete** on integration branch:
  - Track merge (`feat/annotate-react` + `feat/compare-react`)
  - Cross-mode navigation (Annotate ↔ Compare)
  - Store persistence regression coverage
  - API regression suite + CLEF integration coverage
- **CLEF shipped**:
  - Provider registry in `python/compare/providers/`
  - Compare UI panel in `src/components/compare/ContactLexemePanel.tsx`
  - Server endpoints:
    - `POST /api/compute/contact-lexemes`
    - `GET /api/contact-lexemes/coverage`

## Release Gates (hard)

The following are **manual Lucas gates** and must be respected in order:

- **C5:** LingPy TSV export verification (columns + row counts in browser)
- **C6:** Full browser regression checklist (Annotate waveform/regions/STT + Compare grid/tags/nav)
- **C7:** Cleanup and legacy deletion **blocked until C5 + C6 are explicitly cleared**

Do not start C7 early.

## Branch + Worktree Policy

### Canonical repository path
- `/home/lucas/gh/ArdeleanLucas/PARSE`

### Canonical worktrees
- Integration root: `/home/lucas/gh/ArdeleanLucas/PARSE` → `feat/parse-react-vite`
- Annotate lane: `/home/lucas/gh/worktrees/PARSE/annotate-react` → `feat/annotate-react`
- Compare lane: `/home/lucas/gh/worktrees/PARSE/compare-react` → `feat/compare-react`

### Active development rule
- `feat/annotate-react` and `feat/compare-react` are now merged into integration.
- **New work should branch off `feat/parse-react-vite`.**
- Do not commit new feature work on stale track branches.

## Ownership + Coordination

Historical split remains useful for boundaries:

- ParseBuilder domain: Annotate + shared platform
- Oda domain: Compare mode components/stores/hooks

However, on integration branch, coordinate shared-surface edits.

### Shared surfaces requiring coordination before commit
- `src/api/client.ts`
- `src/api/types.ts`
- `python/server.py`

## Safe Work Now (pre-C6)

- Add provider test coverage under `python/compare/providers/test_*.py`
- Improve Lexibank/WOLD setup docs and CKB coverage strategy
- Expand provider metadata and scholarly-source coverage plans

## Do Not Touch

- `src/components/compare/*` (ContactLexemePanel + compare components currently stable)
- `python/server.py` beyond existing CLEF endpoints
- `config/sil_contact_languages.json` directly (runtime output file)
- Any C7 cleanup/deletion before C5+C6 signoff

## Test Gates (pre-push)

Run both before pushing integration changes:

```bash
npm run test -- --run
./node_modules/.bin/tsc --noEmit
```

Expected floor: **>=102 passing tests** and clean TypeScript compile.

## Baseline Architecture

- Frontend: React 18 + TypeScript + Vite + Zustand
- Backend: Python server on `127.0.0.1:8766`
- Data: speaker annotations JSON + enrichments + LingPy export pipeline

---

If pivot status changes (new phase completion, gating updates, ownership shifts), update this file immediately to prevent stale coordination instructions.
