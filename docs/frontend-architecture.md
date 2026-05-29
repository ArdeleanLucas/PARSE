# Frontend Architecture

> Last updated: 2026-05-09
>
> Frontend-specific companion to [Architecture & Data Model](./architecture.md). Detailed rule contracts should stay in code-level JSDoc where possible.

## Sidebar grouped-variant visibility

The source of truth for grouped/source-item variant visibility is the JSDoc on `isConceptVariantVisibleInSidebar()` in `src/lib/sidebarVisibility.ts`.

At a high level, the concept sidebar applies the same rules that PR #316 introduced for speaker-scoped sidebar variant visibility:

1. speaker-scoped sidebars hide variants whose raw `conceptKey` is not elicited for the active sidebar speaker;
2. selected tag filters require the same raw variant key to carry every selected tag in the active tag scope;
3. variants remain visible by default when neither rule rejects them.

`ParseUI.tsx` owns the current UI state and passes those state values into the pure helper. `ConceptSidebar.tsx` receives the resulting predicate through `isConceptVariantVisibleInSidebar` and uses it only to derive visible child rows and the first selectable visible variant, preserving the component as a render surface rather than a state owner.

## Realization selection and elicitation intervals

`ParseUI.tsx` now stores the active concept as a `selectedRealizationKey` (`<concept_id>:<interval_index>`) and derives the older concept-level key from it. `ConceptSidebar` emits these keys from A/B/C realization chips, right-panel speaker forms consume the interval index to show the matching IPA/ORTH/audio data, and `AnnotateView` threads the same focus into its editable interval lookup.

Adding another elicitation creates a new interval on the same canonical `concept_id`. Deleting an elicitation calls `POST /api/annotations/intervals/delete` and removes only that realization plus matching tier rows at the same time span. The legacy duplicate-concept row path is intentionally gone from the current UI contract.
