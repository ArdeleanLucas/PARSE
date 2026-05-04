# Concept Tags Sidecar Merge-Order Plan — 2026-05-04

## Context

The 2026-05-04 concept-tag work is split across three lanes:

| Lane | Branch / worktree | Responsibility |
|---|---|---|
| `parse-back-end` | `feat/concept-tag-per-speaker-confirm-time-be` in `/home/lucas/gh/worktrees/PARSE/concept-tag-per-speaker-confirm-time-be` | Add `concept_tags: Dict[str, List[str]]` to AnnotationRecord normalization, default empty records, and JSON round-trip tests in `python/server_routes/annotate.py` / backend tests. |
| `parse-front-end` | `feat/concept-tag-per-speaker-confirm-time-fe` in `/home/lucas/gh/worktrees/PARSE/concept-tag-per-speaker-confirm-time-fe` | Move per-speaker concept-tag membership from global `tagStore` concept arrays to `AnnotationRecord.concept_tags`, and split “Mark done” from boundary-only “Confirm time.” |
| `parse-coordinator` | `docs/concept-tag-sidecar-architecture` in `/home/lucas/gh/worktrees/PARSE/concept-tag-per-speaker-confirm-time-coord` | Publish the collision audit, sidecar architecture note, and this merge-order plan. No FE/BE source changes. |

## Preferred merge order

1. **Merge parse-back-end first.**
   - This is the persistence/schema unlock.
   - It is additive: existing records without `concept_tags` remain valid and should normalize as absent/empty.
   - Once merged, the server can accept FE writes that include `concept_tags` and round-trip them to disk instead of dropping the unknown top-level field.

2. **Merge parse-front-end second.**
   - This changes user-visible confirmation behavior and starts writing `AnnotationRecord.concept_tags`.
   - Landing it after the BE PR avoids a window where the React client writes a sidecar that a still-old server silently removes during save normalization.

3. **Merge or keep the coordinator docs PR independently.**
   - This docs PR does not implement the feature.
   - It is safe to merge before, between, or after the implementation PRs, but it should not be treated as a substitute for either lane’s tests.

## Safety notes

Either implementation order is structurally additive in the sense that old records do not need a migration before the field exists. However, **BE-first is the operationally correct order** because PARSE persistence is server-normalized. A FE-first merge could let the UI construct `concept_tags` locally while the old backend writes a normalized record that lacks that unknown sidecar.

## Drift / blocker definition

Block or re-audit before merging implementation if any of the following becomes true:

- The collision audit finds a pre-existing top-level `concept_tags` field in live workspace annotation records.
- Either lane changes the sidecar shape away from `Record<string, string[]>` / `Dict[str, List[str]]`.
- `concept_tags` is moved into `tiers` or encoded as a TextGrid/Praat tier.
- The frontend keeps global tag membership as the write source for confirmed concept state after adding the sidecar.
- The backend accepts `concept_tags` but does not round-trip it through the annotation save/load path.

## Sign-off expectation

Before Lucas merges the implementation sequence, use the lane PRs’ own validation evidence:

- Backend: targeted/full pytest, ruff, and isolated-port boot smoke from the BE PR.
- Frontend: `npx vitest run`, `./node_modules/.bin/tsc --noEmit`, and `npm run build` from the FE PR.
- Coordinator: docs-only scope check plus the collision-audit report in `docs/reports/2026-05-04-concept-tags-collision-audit.md`.