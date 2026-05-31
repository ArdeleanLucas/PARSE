# Canonical-character collapse plan

## Scope and current contract

MC-439-B is an analysis/design lane only. It adds an integrity report that quantifies the current BEAST2/NEXUS character inflation caused by duplicate concept ids, but it does **not** change matrix export, cognate computation, interactive storage, or workspace data.

The target contract for MC-439-C is:

> Emit one phylogenetic character family per canonical concept identity, where canonical identity is `normalize_cross_survey_gloss(concept_en)` from `python/concept_linking.py`.

The audit deliberately reuses `build_canonical_gloss_index` / `normalize_cross_survey_gloss` rather than introducing another gloss normalizer.

## What the current exporter does

Current NEXUS generation in `python/ai/tools/export_tools.py::build_nexus_text` builds one binary character for each retained `(concept_id, cognate_group)` pair:

1. Read top-level `parse-enrichments.json:cognate_sets`.
2. Read `manual_overrides.cognate_sets`.
3. Build the union of manual keys followed by auto keys.
4. For each key, use the manual concept block when it is a dict; otherwise use the auto block.
5. Retain only list-valued, non-empty groups.
6. Emit labels as `{concept_id}_{group}` and set `DIMENSIONS NCHAR` to the number of retained `(concept_id, group)` pairs.

That is correct for id-keyed interactive state, but it over-weights duplicated real-world concepts in phylogenetic export. If `hair` exists under four ids, the matrix can currently receive characters for each id.

## Integrity classes

The MC-439-B audit classifies every multi-id canonical-gloss group into these implementation classes:

- **Class 1 — safe duplicate:** all member rows share the same `source_survey` + `source_item`, and their current export columns are byte-identical after export-style manual override precedence. These are safe to column-deduplicate because the matrix contribution is already identical.
- **Class 2 — same source item, different partition:** member rows share `source_survey` + `source_item`, but their current export columns differ. These are not safe to union.
- **Class 3 — cross-survey / cross-source duplicate:** member rows differ by `source_survey` or `source_item`. These are invisible to same-survey grouping in Compare and are not safe to union.

The audit separately reports:

- `safe_union`: all member columns are byte-identical.
- `needs_recluster`: member columns differ; the follow-up must re-cluster pooled forms.

## Critical finding: group letters are not cross-comparable

Cognate group letters are assigned per numeric concept id in `python/compare/cognate_compute.py`. LingPy receives rows partitioned by concept id and returns group labels (`A`, `B`, ...). The label `A` under concept id `249` is not evidence of homology with label `A` under concept id `1`; each id's letters are local to its own clustering run.

Therefore MC-439-C must **not** collapse Class 2 or Class 3 by unioning existing `A`/`B` columns. That would assert homology between independently-lettered partitions.

Only Class 1 can be collapsed by byte-identical column deduplication. Class 2 and Class 3 require re-clustering the pooled forms for all member concept ids in one canonical-concept computation before emitting a collapsed matrix character set.

## Recommended MC-439-C implementation approach

Recommended approach: **export-only canonical collapse with pooled re-clustering, while preserving id-keyed storage.**

1. Keep persisted `cognate_sets`, `similarity`, and `manual_overrides.speaker_flags` keyed by numeric concept id.
2. Add a canonical export path that builds canonical groups from `concepts.csv` using `build_canonical_gloss_index`.
3. For each canonical key:
   - If all member concept-id columns are byte-identical, deduplicate the identical columns.
   - Otherwise, pool forms from all member ids and run one canonical clustering pass for the pooled forms before matrix emission.
4. Keep the re-clustering implementation near `python/compare/cognate_compute.py`, because that module already owns `FormRecord`, LingPy invocation, and group-label assignment. Export code should call a focused helper rather than duplicating LingPy mechanics inside `export_tools.py`.
5. Do not persist canonical export clusters back into the interactive `parse-enrichments.json` unless a later coordinated FE+BE migration explicitly changes the storage contract.

This means MC-439-C should likely introduce a helper such as `compute_canonical_cognate_sets(...)` or `build_canonical_export_characters(...)` in/near `compare.cognate_compute`, then call it from the NEXUS exporter. The helper can still return export-ready characters without re-keying the workspace's interactive state.

## FE/storage key-contract impact

The MC-439-A change set inspected for this lane (`src/lib/speakerForm.ts` on PR #606's branch; GitHub reported PR #606 as open at MC-439-B implementation time) makes the selected variant's numeric concept id the `SpeakerForm.cognateKey` used for cognate, similarity, and per-speaker flag reads/writes:

- merged concept: `concept.mergedKeys[selectedIdx]`
- grouped source item: `concept.variants[selectedIdx].conceptKey`
- singleton: `concept.key`

`readCompareDecisionFields` then reads `similarity[cognateKey]`, `manual_overrides.cognate_sets[cognateKey]` / `cognate_sets[cognateKey]`, and `manual_overrides.speaker_flags[cognateKey]`.

Re-keying persisted `cognate_sets` from numeric ids to canonical-gloss keys would break those lookups until the frontend resolver and all write paths are updated in lockstep. It would also complicate legacy workspaces with id-keyed manual overrides.

Recommendation: choose option **(a) export-only collapse with id-keyed storage preserved** for MC-439-C. It fixes the BEAST2/NEXUS weighting bug without invalidating the interactive Compare contract. Option **(b) canonical storage re-key** should be reserved for a later coordinated FE+BE migration if Lucas wants canonical keys everywhere.

## Manual override and backward-compatibility note

Existing manual cognate overrides are id-keyed. MC-439-C must preserve them as user decisions, but cannot blindly union their group letters across ids unless the columns are byte-identical.

Recommended handling:

- Class 1 / `safe_union`: identical manual/auto columns may be deduplicated directly for export.
- Class 2/3 / `needs_recluster`: treat id-keyed manual overrides as evidence attached to their original forms, then re-cluster pooled forms or require a canonical override surface in a later migration. Do not assert that `A` under one id equals `A` under another id.
- Persisted data remains unchanged; any canonical export clusters are generated for export output only.

## MC-439-B fixture headline

The in-repo audit fixture at `python/tests/fixtures/canonical_character_audit/` has three affected canonical concepts:

- Current NCHAR: 9
- Projected NCHAR after canonical collapse: 3
- NCHAR inflation: 6
- Class counts: Class 1 = 1, Class 2 = 1, Class 3 = 1
- `safe_union` groups: 1
- `needs_recluster` groups: 2

The live workspace is intentionally not read by this PR. Lucas can generate live numbers with:

```bash
PYTHONPATH=python python3 -m concept_character_audit /path/to/workspace
```

## Follow-up

MC-439-C should implement the backend collapse after Lucas reviews the audit numbers. The locked approach is:

- deduplicate only byte-identical Class 1 columns;
- re-cluster pooled forms for Class 2/3;
- keep interactive storage numeric-id-keyed unless a separate FE+BE contract migration is explicitly approved.
