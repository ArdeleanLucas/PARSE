# MC-343 Sidebar speaker scoping in Annotate mode

## Objective
Implement the 2026-05-07 parse-front-end handoff: in Annotate mode, the left concept sidebar defaults to the active speaker's elicited concept subset, has a Show all toggle, and the topbar reviewed denominator becomes per-speaker elicited count.

## Source of truth
- Handoff: `/home/lucas/gh/tarahassistant/PARSE-rebuild/.hermes/handoffs/parse-front-end/2026-05-07-sidebar-speaker-scoping.md`
- Base: `origin/main` at `6cf5d38`

## Scope
- Add `src/lib/speakerElicitedConcepts.ts` with tests.
- Extend `ConceptSidebar` props/rendering for scoped/unscoped speaker list behavior.
- Wire `ParseUI.tsx` active annotation record, localStorage mode defaults, sidebar props, and topbar per-speaker counter.
- Extend component and shell tests with RED/GREEN coverage.

## Out of scope
- Backend changes.
- Compare mode filtering changes beyond defaulting scope off.
- Duplicate concept A/B UX.
- Browser smoke/screenshots.

## Validation
- Focused Vitest for new helper/sidebar/shell tests.
- Full `npx vitest run`.
- `./node_modules/.bin/tsc --noEmit` or `npm run check`.
- `npm run build`.
- `git diff --check`.
