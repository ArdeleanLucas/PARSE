# MC-354 Grouped Concept Key Collision

## Objective
Fix grouped sidebar concept interval lookup so grouped `key` values derived from `source_item` are not compared against annotation-tier master `concept_id` values.

## Scope
- Apply option A from the handoff: skip `concept.key` inside `underlyingConceptKeys()` when grouped variants are present.
- Preserve variant, merged key, and merged variant master-id matching.
- Add regression coverage for the exact Saha01-style `source_item="298"` vs master `concept_id="298"` collision.

## Files
- `src/lib/parseUIUtils.ts`
- `src/lib/parseUIUtils.test.ts`
- `src/components/annotate/annotate-views/shared.test.ts`

## Validation
- Focused RED/GREEN Vitest for new regressions.
- `npx vitest run`
- `./node_modules/.bin/tsc --noEmit`
- `npm run build`
- `git diff --check`
