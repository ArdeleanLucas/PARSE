# AGENTS.md — PARSE React + Vite Pivot (2026)

## Current State

PARSE is pivoting from vanilla JS to a modern **React 18 + TypeScript + Vite + Zustand** frontend while keeping the existing Python backend (`python/server.py` on port 8766) **frozen**. 

Two specialized agents now run in parallel:

- **ParseBuilder** — owns Annotate Mode (`src/components/annotate/`, most stores, shared components, routing, `src/api/client.ts`, `src/api/types.ts`, `App.tsx`, Vite config, etc.).
- **Oda** — owns **Compare Mode** (`src/components/compare/*`, `tagStore.ts`, `enrichmentStore.ts`, `useExport.ts`, `useComputeJob.ts`). Prompt entry point: `docs/plans/oda/oda-core.md`. Per-phase files: `docs/plans/oda/phase-0.md`, `docs/plans/oda/b1-concept-table.md` through `b9-compare-mode.md`, `docs/plans/oda/rules.md`, `docs/plans/oda/coordination.md`.

You **must not** cross file boundaries. ParseBuilder never touches Oda’s files and vice versa. Coordination is restricted to Phase 0 (shared contract) and Phase C (final merge).

**Oda’s prompt was condensed** on 2026-04-08 because the original was too large. It now consists of 11 dense paragraphs covering ownership, model preference (Gemini Flash + 3.1 Pro), client protocol, store rules, immutability, quality gates, and explicit Lucas sign-off on completion.

## Pivot Status (updated 2026-04-08)

**Track A (Annotate Mode) — COMPLETE.** A1-A10 committed on `feat/annotate-react` (9 commits, e9cf22f through ce5d6b1). 47 tests passing, 0 tsc errors, Vite proxy confirmed. A11 (browser integration) pending — Lucas must verify in browser.

**Track B (Compare Mode) — B1-B6 COMPLETE, B7-B9 pending.** `feat/compare-react` has 2 commits (e8a446c scaffold, 44ee8de B1-B6). 32 new tests, full suite 79 tests passing, 0 tsc errors. Remaining: B7 (useExport), B8 (CompareMode root), B9 (browser integration — Lucas).

**Note:** Oda’s original B1-B6 submission was audited and found incomplete — wrong branch, 3/6 files missing, 3/6 were stubs with no real logic, 0 tests. All six components were rebuilt by ParseBuilder on `feat/compare-react`. The only salvaged artifact was `tagStore.ts` (solid implementation, moved to the correct branch).

**Shared barrel:** `src/components/shared/index.ts` now exists. Oda’s files can import shared primitives from `’../shared’`.

**Branch status:** `feat/annotate-react` has 9 commits. `feat/compare-react` has 2 commits.

## Project Structure (React + Vite)

```
src/
├── components/
│   ├── compare/          ← Oda owns all of this + tests
│   ├── annotate/         ← ParseBuilder owns
│   └── shared/           ← ParseBuilder owns (request primitives from them)
├── stores/               ← Split between agents
├── hooks/                ← Oda owns useExport + useComputeJob
├── api/
│   ├── client.ts         ← ParseBuilder (typed fetch wrapper)
│   └── types.ts          ← ParseBuilder (shared interfaces)
├── App.tsx, main.tsx
├── vite.config.ts
├── index.html
└── package.json
```

Python backend, audio files, and config directories remain unchanged.

## Repo Location

`/home/lucas/gh/ardeleanlucas/parse` — use this as `workdir` for all Codex/subagent calls.

## Branches

- `feat/annotate-react` — ParseBuilder's Track A branch
- `feat/compare-react` — Oda's Track B branch
- `feat/parse-react-vite` — integration merge target (ParseBuilder leads Phase C only)
- Never commit to `main` during the pivot.

## Before You Write Code (Mandatory)

1. Read `docs/plans/react-vite-pivot.md` — full dual-agent architecture and plan.
2. If you are **Oda**: load `docs/plans/oda/oda-core.md` first. Then load only the specific `docs/plans/oda/b{N}-*.md` file for your current task. Load `docs/plans/oda/rules.md` with every task.
3. If you are **ParseBuilder**: your Track A plan is in `docs/plans/react-vite-pivot.md` under "Track A".
4. **Phase 0 is a hard blocker.** No component code until `npm run dev` starts, `curl localhost:5173/api/config` returns JSON, and `npx tsc --noEmit` passes. Stop and fix if any of these fail.
5. Always declare your exact model before spawning any coding sub-agent.

## File Ownership (Strict)

**Oda (Compare Mode) owns only:**
- `src/components/compare/*` (all components + tests)
- `src/stores/tagStore.ts`, `src/stores/enrichmentStore.ts`
- `src/hooks/useExport.ts`, `src/hooks/useComputeJob.ts`

**ParseBuilder owns everything else.**

Oda may **read** any file but must **never write** outside the list above. Request shared primitives or new `client.ts` functions from ParseBuilder with exact interfaces.

## Coding Standards (React Pivot)

- **TypeScript strict** — no `any` without explicit comment.
- **Zustand** for all persistent state. Never use `useState` for store data.
- Vitest + Testing Library for all components and hooks.
- All API calls via typed `client.ts` functions only.
- No inline styles for layout. No CSS frameworks.
- `persist()` after every tag mutation. Proper v1 → v2 localStorage migration.
- LingPy TSV export is P0 — verify `/api/export/lingpy` before implementing `useExport`.

**Oda Model Routing (codified):** `gemini-2.5-flash` for most work. `gemini-2.5-pro` for B1 (ConceptTable) and B4 (TagManager) only. Never default to Claude unless both Gemini options fail twice.

## What NOT To Do

- Do not cross file ownership boundaries.
- Do not modify the frozen Python backend.
- Do not merge your own branch — ParseBuilder leads Phase C.
- Do not ship without Lucas personally verifying the full browser checklist.
- Do not use Claude models unless both Gemini options have failed twice.

## Completion Gate (Track B — Compare Mode)

Oda must deliver a clean `feat/compare-react` branch where:
- All tests pass (`npm run test`)
- TypeScript compiles cleanly
- Lucas has verified every item on the browser checklist (grid, cognate operations, tags persist, compute jobs, LingPy export, no console errors, etc.)

Until Lucas signs off, Track B is not complete.

---

**This AGENTS.md reflects the React pivot.** Old vanilla JS instructions archived in git history.
Oda's entry point: `docs/plans/oda/oda-core.md`. Full plan: `docs/plans/react-vite-pivot.md`.
Update this file when pivot status or agent responsibilities change.