# PARSE React + Vite Pivot — Historical Reference

> **Status:** the React/Vite pivot has landed on `main`. This doc is kept as
> historical context only. It preserves the `js/` → React decomposition map
> (the mechanical migration checklist used during the pivot) so future work
> can verify that every legacy module has a typed React counterpart.
>
> The live API contract lives in **`AGENTS.md` § Client/Server Contract Surface**.
> Do not duplicate that table here — it drifts otherwise.

---

## Background (historical, for context)

- **Original scope:** replace the vanilla-JS monolith (36,951 lines across `parse.html`, `compare.html`, and 25 JS modules) with React + Vite, keeping the Python backend (`127.0.0.1:8766`) unchanged.
- **Execution:** dual-agent — ParseBuilder (Track A, Annotate) and Oda (Track B, Compare). Tracks agreed a shared contract in Phase 0, worked in parallel, and integrated in Phase C.
- **Constraint:** no emoji in the UI; annotation timestamps are immutable.
- **Result:** React SPA in `src/ParseUI.tsx` is the sole runtime frontend. Stage 3 / PR #58 removed the remaining vanilla-JS runtime (`js/`, `parse.html`, `compare.html`, `review_tool_dev.html`, legacy launchers).

Historical branch names like `feat/parse-react-vite`, `feat/annotate-react`, `feat/compare-react` referenced throughout the original plan are merged/deleted. Do not recreate them; branch new work from `origin/main`.

---

## `js/` → React migration map

Canonical record of which legacy module became which React surface. Every row has landed.

| Legacy file | Lines | Track | React replacement |
|---|---|---|---|
| `parse.html` | 3,202 | A | Vite entry via `src/main.tsx` → `src/App.tsx` |
| `compare.html` | 1,591 | B | Vite entry via `src/main.tsx` → `src/App.tsx` |
| `js/annotate/parse.js` | 1,871 | A | Decomposed into `src/ParseUI.tsx` + annotate components |
| `js/annotate/waveform-controller.js` | 734 | A | `src/hooks/useWaveSurfer.ts` |
| `js/annotate/region-manager.js` | 933 | A | `src/components/annotate/RegionManager.tsx` |
| `js/annotate/annotation-panel.js` | 1,037 | A | `src/components/annotate/AnnotationPanel.tsx` |
| `js/annotate/transcript-panel.js` | 765 | A | `src/components/annotate/TranscriptPanel.tsx` |
| `js/annotate/suggestions-panel.js` | 885 | A | `src/components/annotate/SuggestionsPanel.tsx` |
| `js/annotate/import-export.js` | 807 | A | `src/hooks/useImportExport.ts` |
| `js/annotate/onboarding.js` | 663 | A | `src/components/annotate/OnboardingFlow.tsx` |
| `js/annotate/fullscreen-mode.js` | 620 | A | **Not ported.** Feature dropped from React scope — if still needed, open a scoped issue before Stage 3 deletion. |
| `js/annotate/video-sync-panel.js` | 1,376 | A | **Not ported.** Feature dropped from React scope — if still needed, open a scoped issue before Stage 3 deletion. |
| `js/compare/compare.js` | 4,654 | B | Decomposed into `src/ParseUI.tsx` + compare components |
| `js/compare/concept-table.js` | 873 | B | `src/components/compare/ConceptTable.tsx` |
| `js/compare/cognate-controls.js` | 854 | B | `src/components/compare/CognateControls.tsx` |
| `js/compare/borrowing-panel.js` | 1,678 | B | `src/components/compare/BorrowingPanel.tsx` |
| `js/compare/enrichments.js` | 1,557 | B | `src/components/compare/EnrichmentsPanel.tsx` |
| `js/compare/speaker-import.js` | 2,147 | B | `src/components/compare/SpeakerImport.tsx` |
| `js/shared/annotation-store.js` | 2,587 | A | Zustand `src/stores/annotationStore.ts` |
| `js/shared/tags.js` | 845 | B | Zustand `src/stores/tagStore.ts` + `TagManager.tsx` |
| `js/shared/ai-client.js` | 909 | A | `src/api/client.ts` (typed) |
| `js/shared/project-config.js` | 371 | A | Zustand `src/stores/configStore.ts` |
| `js/shared/audio-player.js` | 269 | A | absorbed into `useWaveSurfer` |
| `js/shared/chat-client.js` | 1,430 | A | `src/components/annotate/ChatPanel.tsx` + `useChatSession` |
| `js/shared/chat-panel.js` | 885 | A | `src/components/annotate/ChatPanel.tsx` |
| `js/shared/chat-tool-adapters.js` | 639 | A | `src/hooks/useChatSession.ts` |
| `js/shared/spectrogram-worker.js` | 273 | A | `src/workers/spectrogram-worker.ts` |

Stage 3 / PR #58 removed the left-column files from the live repo; the right column is the current runtime surface.

---

## Pointers

- **Live API contract:** `AGENTS.md` § Client/Server Contract Surface.
- **Current execution plan:** `docs/plans/parseui-current-state-plan.md`.
- **Deferred-validation policy (C5/C6/C7):** `AGENTS.md` § Deferred Validation Backlog.
- **Architecture direction:** `docs/desktop_product_architecture.md`.
