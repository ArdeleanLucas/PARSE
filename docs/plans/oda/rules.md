# Rules — Hard Constraints (Load with Every Task)

> Every rule here is a blocker. Violation = stop and fix before continuing.
>
> **Historical note (post-pivot merge):** this file documents the original Compare-track lane. References to `feat/compare-react` and `feat/parse-react-vite` are historical lane notes, not the current default branch policy. New work now branches from `origin/main` unless Lucas explicitly asks for a historical lane.

---

## Code Quality

1. **No bare `fetch()` calls.** Every API call goes through `src/api/client.ts`.
   No exceptions — not in components, not in hooks, not in stores.

2. **No `window.PARSE` references.** The old global namespace is dead in React.

3. **No `localStorage` reads/writes** except inside `tagStore.persist()` and
   `tagStore.hydrate()`. Those are the only two places.

4. **No emoji in the UI.** Text labels only. This is a fieldwork research tool.

5. **TypeScript strict mode.** Every file must compile with `npx tsc --noEmit`
   before it is considered done.

6. **No `any` types** unless unavoidable. If you use `any`, add an inline comment
   explaining exactly why.

7. **No inline styles for layout.** Use CSS classes. Plain CSS modules or a
   utility class string. No external CSS frameworks.

---

## Architecture

8. **Zustand is the only state for data.** No `useState` for data that belongs
   in a store. `useState` is allowed only for pure UI state (modal open/close,
   which tab is active).

9. **Store shapes are immutable.** Agreed in Phase 0. You implement them, you do
   not redesign them. If you need a shape change, file an amendment with Lucas
   in writing before changing any code.

10. **Timestamps are immutable.** `start` and `end` on `AnnotationInterval` are
    set once and never changed. Display them, never mutate them.

11. **Concept IDs are stable identifiers.** Never normalize, trim, lowercase,
    or transform a concept ID. The entire pipeline — annotations, enrichments,
    LingPy export, BEAST2 — breaks silently if IDs drift.

12. **`enrichmentStore.save()` is the only write path for enrichment data.**
    No direct POST to `/api/enrichments`.

13. **`tagStore.persist()` after every mutation.** A tag that is not persisted
    is lost on page reload. Fieldwork data cannot be lost.

14. **LingPy TSV export is P0.** If `/api/export/lingpy` returns 404, stop and
    report immediately to ParseBuilder and Lucas. Do not ship without it.

---

## Branch and File Discipline

15. **Historical lane note:** the original Compare track worked on `feat/compare-react`.
    Do not treat that as the current default policy; for new work, branch from
    `origin/main` unless Lucas explicitly revives the historical lane.

16. **Write only to your owned files.** Never touch:
    `src/components/annotate/`, `src/hooks/useWaveSurfer.ts`,
    `src/stores/annotationStore.ts`, `src/stores/playbackStore.ts`,
    `src/stores/configStore.ts`, `src/stores/uiStore.ts`,
    `src/api/client.ts`, `src/api/types.ts`,
    `vite.config.ts`, `package.json`, `index.html`, `src/App.tsx`,
    or anything under `python/`.

17. **Do not merge into historical pivot branches** such as `feat/parse-react-vite`.
    That lane has already been merged and deleted. Current work should go back to
    `main` via PRs from `origin/main`-based feature branches.

---

## Testing

18. **Every component and hook has a co-located test file.** Tests in
    `src/components/compare/` and `src/hooks/`.

19. **`npm run test` must pass with zero failures** before Track B is done.

20. **`npx tsc --noEmit` must pass with zero errors** before Track B is done.
