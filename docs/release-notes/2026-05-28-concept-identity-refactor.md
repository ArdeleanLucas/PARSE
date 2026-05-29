# Concept identity refactor release notes

> Last updated: 2026-05-28. These notes summarize MC-418, the concept-identity refactor that removed stored per-speaker variant suffixes from canonical concept labels and moved elicitation letters to render-time / interval-order behavior.

## Summary

PARSE no longer treats `(A)`, `(B)`, or similar per-speaker elicitation suffixes as part of the global `concept_en` identity. A concept row is now identified by its source slot and canonical base label:

```text
concept identity = (source_survey, source_item, canonical base label)
```

Variant letters are computed when PARSE renders a speaker's intervals. Two different speakers can each have one elicitation of `big` and both see the bare label. A single speaker with multiple intervals on the same `concept_id` sees `A`, `B`, and later letters according to interval start-time order. The letter is not stored in `concepts.csv`, annotation JSON, or tags.

## Default-mode export regression status (updated 2026-05-28)

Issue [#562](https://github.com/ArdeleanLucas/PARSE/issues/562) recorded a default-mode review export regression found after the MC-418 release-note PR merged: default export initially had empty IPA/contact-reference coverage, duplicate `concept_en` entries, and an over-broad speaker set compared with the anchored reviewer output.

That warning is now superseded by MC-422/MC-424 fixes and acceptance evidence: PRs [#568](https://github.com/ArdeleanLucas/PARSE/pull/568), [#569](https://github.com/ArdeleanLucas/PARSE/pull/569), [#570](https://github.com/ArdeleanLucas/PARSE/pull/570), [#572](https://github.com/ArdeleanLucas/PARSE/pull/572), [#573](https://github.com/ArdeleanLucas/PARSE/pull/573), and [#574](https://github.com/ArdeleanLucas/PARSE/pull/574) restored default-mode parity for the reviewer subset. The acceptance report at [`docs/reports/2026-05-28-mc-422-acceptance.md`](../reports/2026-05-28-mc-422-acceptance.md) records 82 concepts / 6 speakers, 492/492 IPA forms, 486/492 ortho/audio forms, 81/82 Arabic refs, 81/82 Persian refs, and zero anchored-present/default-missing rows after MC-424-A.

The deployed `review_tool` HEAD `2ac21dd` (MC-415-D anchored state) remains the rollback baseline until Lucas pushes the prepared default-mode review_tool commit. Anchored-mode export still exists through deprecated `--legacy-anchor`, but it is no longer the only safe data path.

## Task and PR inventory

**MC Task:** MC-418 — Concept identity refactor  
**Issues resolved:** [#529](https://github.com/ArdeleanLucas/PARSE/issues/529), [#541](https://github.com/ArdeleanLucas/PARSE/issues/541), [#537](https://github.com/ArdeleanLucas/PARSE/issues/537), [#533](https://github.com/ArdeleanLucas/PARSE/issues/533)  
**Internal plan:** `.hermes/plans/2026-05-28-concept-identity-refactor.md`  
**Shipped:** 2026-05-28

| Lane | PR | Status | Scope |
|---|---:|---|---|
| MC-418-A | [#546](https://github.com/ArdeleanLucas/PARSE/pull/546) | Merged | Frontend `assignVariantLetters` helper plus cross-language fixture. |
| MC-418-B | [#550](https://github.com/ArdeleanLucas/PARSE/pull/550) | Merged | Frontend wiring and `+ Add elicitation` UX replacing the old duplicate-variant action. |
| MC-418-C | [#547](https://github.com/ArdeleanLucas/PARSE/pull/547) | Merged | Backend `concept_canonical.py` consolidation, importer guard, and compare-bundle call-site consolidation. |
| MC-418-D | [#551](https://github.com/ArdeleanLucas/PARSE/pull/551) | Merged | Slot-aware concept allocator and downstream survey/item threading. |
| MC-418-E | [#552](https://github.com/ArdeleanLucas/PARSE/pull/552) | Merged | Removal of duplicate-concept route, schema, client, and UI affordances. |
| MC-418-F | [#554](https://github.com/ArdeleanLucas/PARSE/pull/554) | Merged | Migration script core and issue #541 prefix handling. |
| MC-418-G | [#556](https://github.com/ArdeleanLucas/PARSE/pull/556) | Merged | Migration verification, idempotence, MCP wrapper, and Fail01 regression. |
| MC-418-H | [#548](https://github.com/ArdeleanLucas/PARSE/pull/548) | Merged | `export_review_data` MCP/chat tool exposure for issue #533. |
| MC-418-I | [#558](https://github.com/ArdeleanLucas/PARSE/pull/558) | Merged | `--legacy-anchor` deprecation path and MC-415-C exporter-strip removal for issue #537. |
| MC-418-J | [#559](https://github.com/ArdeleanLucas/PARSE/pull/559) | Merged | These release notes and board parent close-out. |
| MC-418-K | [#557](https://github.com/ArdeleanLucas/PARSE/pull/557) | Merged | Post-live-run migration fix: canonicalize standalone `(X)` rows and re-key `survey-overlap.json`. |

The original MC-418-J handoff was drafted before MC-418-K existed. MC-418-K is included here because it changed the final shipped migration behavior and is part of the same release boundary.

### Sidecar followups

| Lane | PR | Status | Scope |
|---|---:|---|---|
| MC-419-A | [#549](https://github.com/ArdeleanLucas/PARSE/pull/549) | Merged | Removed stale AGENTS.md guidance that deselected ortho cascade/default tests. |
| MC-419-B | [#555](https://github.com/ArdeleanLucas/PARSE/pull/555) | Merged | Removed the CI workflow deselect and extended the backend-validation guidance regression. |
| MC-420-A | [#553](https://github.com/ArdeleanLucas/PARSE/pull/553) | Merged | Fixed body indentation in `python/ai/tools/export_tools.py`. |

MC-420 is closed with this release because the only board sublane present at close-out was MC-420-A and PR #553 is merged. Later cleanups such as `ConceptRegistry.id_to_row`, legacy `label_to_id` retirement, or minor hover affordances should be opened as fresh tasks if Lucas wants them.

## API surface deltas

### Removed backend API and schemas

- `POST /api/concepts/{conceptId}/duplicate` was removed. Unknown concept sub-resource routes now return `404` with `Unknown API endpoint` instead of routing to duplicate behavior.
- OpenAPI path `/api/concepts/{conceptId}/duplicate` was removed.
- OpenAPI component `ConceptDuplicateResponse` was removed.
- `python/concepts_io.py::duplicate_concept_variant` was removed.
- `python/concepts_io.py::_source_item_variant_suffixes` was removed.
- Duplicate-only helpers `_first_free_letter`, `_next_free_variant_label`, `_backup_path`, and `_max_numeric_id` were removed.
- `python/concepts_io.py::ConceptDuplicateError` was removed.
- `python/server_routes/exports.py::_copy_concept_tags_to_sibling`, `_mirror_global_tag_concepts_to_sibling`, and `_api_post_concept_duplicate` were removed.

### Removed frontend API and UI surface

- The concept-sidebar context-menu action `Duplicate (split into next variant)` was removed.
- `src/api/contracts/concepts.ts::duplicateConcept` was removed.
- TypeScript interface `ConceptDuplicateResponse` was removed.
- Duplicate-specific loaded-store protection was removed from `src/ParseUI.tsx`: `seedLoadedDuplicateSiblingTags`, `recentlyDuplicatedSibling*`, `freshDuplicateKeysBySpeaker`, and `EMPTY_FRESH_KEYS`.
- Duplicate-specific chip props and styling were removed from `src/components/shared/VariantChip.tsx`: `recentlyDuplicated`, `showNew`, `VARIANT_CHIP_RECENT_CLASS`, and the `NEW` badge.
- `src/lib/sidebarVisibility.ts::activeSpeakerFreshKeys` was removed.

### New backend API, tools, and helpers

- `python/concept_canonical.py` now owns shared concept-label canonicalization:
  - functions: `variant_suffix`, `variant_stem`, `strip_bare_variant_suffix`, `strip_cue_prefix`, `canonicalize_label`, `label_key`, and `assign_variant_letters`
  - regexes: `VARIANT_SUFFIX_RE`, `BARE_VARIANT_RE`, and `LEADING_CUE_PREFIX_RE`
- `python/scripts/migrate_concept_suffix_pollution.py` provides the one-shot workspace migration CLI.
- `python/migration/concept_suffix_pollution.py` provides the importable migration engine.
- MCP/chat tool `migrate_concept_suffix_pollution` exposes the migration through the PARSE tool surface.
- MCP/chat tool `export_review_data` exposes review-tool export generation through the PARSE tool surface.
- `python/concept_registry.ConceptRegistry` now has plural label indexing and triple lookup via `label_to_ids` and `triple_to_id`.
- `python/server_routes/annotate.py::_annotation_interval_survey_item` derives survey/item slot identity while enforcing annotation concept ids.

### New frontend helpers and behavior

- `src/lib/conceptGrouping.ts::assignVariantLetters` computes per-speaker variant letters from annotation interval order.
- The concept-sidebar context menu now offers `+ Add elicitation` to add another interval on the same canonical concept.
- `ParseUI.tsx` now derives `elicitationVariantLabelsByConceptKey` for render-time chip labels.
- `ConceptSidebar.tsx` renders per-speaker variant chips from computed interval-order labels.
- `tests/fixtures/variant-letters.json` pins shared backend/frontend fixture parity for variant-letter ordering.

## Intentional behavior changes

| Area | Previous behavior | Current behavior |
|---|---|---|
| Concept identity | Per-speaker suffixes such as `big (A)` could pollute global `concept_en` identity. | Canonical concept rows store the base label only; speaker-specific letters are derived at render time. |
| Multiple source slots with same label | Casefold-equivalent labels could collapse into one concept id even when they came from different cue/source slots. | The allocator keys by `(source_survey, source_item, canonical label)`, so two distinct source slots can retain distinct ids. |
| Add another elicitation | Users duplicated a global concept row and then risked tag/annotation deadlocks. | Users add another interval on the same concept id; the UI computes variant chips only when needed. |
| Unknown concept sub-resource | Unknown four-part `/api/concepts/*` paths could return `400 Malformed concept path`. | Unknown concept sub-resources return `404 Unknown API endpoint`. |
| Deleting a concept row | Error copy referred to variants in a way that implied a duplicate-row workflow. | Error copy says the canonical concept row is annotated and cannot be deleted. |
| Lexeme-note variant parsing | Bare-letter stripping covered only `[A-D]`. | Bare-letter stripping covers `[A-Z]` for cue files with later variants. |
| Cross-survey gloss normalization | Some parenthetical variants, such as `big (A)`, survived normalization. | Shared canonicalization strips stored variant suffixes while preserving true clarifier parentheses. |
| `export_review_data --legacy-anchor` | Legacy anchor mode remained a live workaround. | The flag is deprecated with a warning; default-mode export has since been repaired and acceptance-tested for the reviewer subset; anchored output remains only the rollback path until the prepared review_tool commit is pushed. |

### Clarifier parentheses after MC-425

The MC-418 canonicalizer removes variant suffixes such as `big (A)` and cue prefixes such as `1.2 big`. Singleton semantic clarifiers such as `green (grass)` or `to bathe (wash oneself)` remain concept labels when there is no same-slot sibling to merge.

MC-425-A/B extended the migration with a same-slot clarifier-collapse pass. Rows sharing `(source_survey, source_item, strip_clarifier(concept_en))` collapse to one canonical id, references are re-keyed, and the removed labels are preserved in δ-format notes (compare notes that record the before/after label change) under `parseui-compare-notes-v1.json`.

Live acceptance is recorded in [`docs/reports/2026-05-28-mc-425-clarifier-collapse-acceptance.md`](../reports/2026-05-28-mc-425-clarifier-collapse-acceptance.md).

## Migration invocation

Run the migration in dry-run mode first:

```bash
python3 python/scripts/migrate_concept_suffix_pollution.py \
  --workspace /path/to/workspace \
  --dry-run
```

Apply it only after reviewing the dry-run summary:

```bash
python3 python/scripts/migrate_concept_suffix_pollution.py \
  --workspace /path/to/workspace
```

Verify an already-migrated workspace:

```bash
python3 python/scripts/migrate_concept_suffix_pollution.py \
  --workspace /path/to/workspace \
  --verify-only
```

Execute the same migration through the HTTP MCP bridge when PARSE is running:

```bash
curl -X POST 'http://127.0.0.1:8766/api/mcp/tools/migrate_concept_suffix_pollution?mode=all' \
  -H 'Content-Type: application/json' \
  -d '{"workspace": "/path/to/workspace", "dry_run": true}'
```

The migration is idempotent. On an already-canonical workspace, dry-run and verify-only paths should plan no rewrites and create no backups. MC-418-K also re-keys `survey-overlap.json` so `concept_survey_links` and `speaker_concept_survey_links` do not point at suffix-polluted ids after concept rows are collapsed.

### Backup behavior

When the migration writes changes, it creates `.bak-<UTC>-pre-suffix-canonicalization` backups beside modified workspace files such as `concepts.csv`, `annotations/*.parse.json`, `parse-tags.json`, and `survey-overlap.json`.

## Known data state after the live migration

The strict MC-418 invariant is met: concept labels should no longer carry stored cue prefixes or stored `(X)` variant suffixes after canonicalization. The live migration also surfaced pre-existing data-quality issues that are not caused by this refactor:

1. **Cross-survey link audit entries.** Some links connect semantically equivalent bare/clarified labels, such as a bare source label linked to a target label with a clarifier parenthetical. These remain meaningful cross-survey links, but a strict label-equality validator can flag them because clarifiers are preserved.
2. **Text-vs-`concept_en` inconsistencies.** Some annotation interval `text` values do not match their referenced canonical `concept_en`. These are annotation-tier data-quality issues for manual triage, not migration blockers.
3. **KLQ 4.18 hard/soft duplicate-row quirk.** The live data contains a pre-existing duplicate/truncated row case that is outside MC-418's suffix-pollution target.

Current follow-up status: MC-422-D added clarifier-tolerant validation/export de-dup, and MC-425-A/B applied same-slot clarifier collapse with provenance notes. Singleton parenthetical rows are still intentionally preserved when there is no same-slot sibling group.

## Cross-references

- Compare Bug 2, the Fail01 `big` empty-IPA case, is covered by the MC-418 migration and frontend regression path.
- Compare Bug 3, the `bird` row yellow-bundle case, was fixed independently before MC-418 by matching compare bundles through `variants.conceptKey` / `mergedKeys` before `concept.key`.
- The 82 phantom thesis tags on minted ids greater than or equal to 643 are addressed by migration tag re-keying.
- Khan snow/ice data corrections remain a manual data-history item; MC-418-G's text-vs-concept audit is the guardrail for analogous future mismatches.
- MC-419 closed the stale ortho-test deselect guidance that had masked full-sweep validation confidence during the MC-418 wave.

## Sharp edges for future work

- `delete_concept_variant` still exists as a destructive canonical-row delete path. It is no longer a duplicate-variant undo operation.
- `lexeme_notes.py::CommentRow.variant` remains for backward compatibility but is no longer load-bearing for concept identity.
- `python/export_review_data.py::_REVIEW_VARIANT_CODE_RE` is intentionally separate from `concept_canonical.VARIANT_SUFFIX_RE`; review-tool parsing needs a broader variant-code regex.
- Future optional cleanups can be opened as fresh tasks: add an `id_to_row` registry index, remove now-redundant singular `label_to_id`, refresh test-count copy, and possibly add variant-letter hover detail.

## MC-418-J verification

MC-418-J close-out verification was run from `/home/lucas/gh/worktrees/coordinator-mc-418-j-release-notes` on 2026-05-28 against `origin/main` commit `3f523386` plus the docs branch. PR #559 was then merged by TrueNorth49 at 2026-05-28T13:11:52Z as merge commit `1cfc24a6`.

| Check | Result |
|---|---|
| Release-note Markdown link audit | Passed for `docs/release-notes/README.md` and this file. |
| `grep -rn "duplicate_concept_variant" python/ src/` | Only absence-test hits in `python/test_concept_duplicate_endpoint.py`. No production hits. |
| `grep -rn "_source_item_variant_suffixes" python/` | Only absence-test hits in `python/test_concept_duplicate_endpoint.py`. No production hits. |
| `grep -rn "_LEADING_NUMBER_PREFIX_RE" python/` | No hits. |
| `grep -rn "test_ortho_section_defaults_cascade_guard.*and.*not" .github/ AGENTS.md` | No hits. |
| `python3 python/scripts/migrate_concept_suffix_pollution.py --workspace /home/lucas/parse-workspace --dry-run` | Passed: 563 rows unchanged, `merge_map entries: 0`, `annotation files rewritten: 0`, `survey-overlap.json entries re-keyed: 0`, `backups: 0`. |
| `PYTHONPATH=python python3 -m pytest python/ -q` | Passed: 1727 passed, 6 skipped, 1 warning, 3 subtests. |
| `npx vitest run` | Passed: 128 files, 1081 passed, 9 skipped. |
| `./node_modules/.bin/tsc --noEmit` | Passed. |
| `npm run build` | Passed; Vite emitted only existing chunk/dynamic-import warnings. |
| `uvx ruff check python/ --select E9,F63,F7,F82` | Passed. |
| `git diff --check` | Passed. |

Verification commands:

```bash
grep -rn "duplicate_concept_variant" python/ src/
grep -rn "_source_item_variant_suffixes" python/
grep -rn "_LEADING_NUMBER_PREFIX_RE" python/
grep -rn "test_ortho_section_defaults_cascade_guard.*and.*not" .github/ AGENTS.md
python3 python/scripts/migrate_concept_suffix_pollution.py --workspace /home/lucas/parse-workspace --dry-run
PYTHONPATH=python python3 -m pytest python/ -q
npx vitest run
./node_modules/.bin/tsc --noEmit
npm run build
uvx ruff check python/ --select E9,F63,F7,F82
git diff --check
```

Close-out interpretation:

- duplicate-removal greps returned no production hits; the remaining `duplicate_concept_variant` / `_source_item_variant_suffixes` hits are absence tests.
- `_LEADING_NUMBER_PREFIX_RE` is absent from `python/`.
- stale ortho deselect guidance is absent from `.github/` and `AGENTS.md`.
- the migration dry-run on `/home/lucas/parse-workspace` planned no rewrites and no backups on the already-canonical workspace.
