# MC-368-A Compare-mode redesign plan — variants × surveys × per-speaker canonical

**Source audit baseline:** `origin/main @ f861f4a5ec594c1704b3c8e22662dff31b6b19ed`
**Scope:** docs-only pre-research audit; no runtime/browser/server use.
**Primary conclusion:** Compare mode needs a first-class **bundle → bucket → variant → per-speaker canonical lexeme** model. Current code has pieces of this in three different places, but no single contract that can show all variants across all elicitation events and drive NEXUS from one selected lexeme per speaker per logical concept.

## Executive summary

1. `src/components/compare/compare-panels/` is a clean modular Compare shell, but it is still flat: `parseConcepts` reads `config.concepts`, `ConceptTable` maps one row per concept, and `lookupEntry` matches concept intervals by display `text` instead of `concept_id` (`shared.ts:35-46`, `ConceptTable.tsx:24-68`, `shared.ts:53-81`).
2. The active monolithic `ParseUI.tsx` Compare surface has newer behavior not represented in the modular shell: source-bucket grouping, multi-realization pills, and `manual_overrides.canonical_realizations` (`ParseUI.tsx:919-925`, `2092-2127`, `2164-2227`, `410-414`). This is useful but not sufficient: it is index-based under a displayed `concept.key`, not an explicit csv-row canonical choice.
3. `concepts.csv` + `survey-overlap.json` currently model rows, global survey links, and speaker survey choices; `speaker_concept_survey_links` is not present on `origin/main` yet (repo-wide search returned 0 matches). MC-367 is expected to add that shape, and MC-368 should consume it instead of inventing a parallel survey-override store.
4. NEXUS export currently reads only `manual_overrides.cognate_sets` / `cognate_sets`, builds one binary character per `(concept, group)`, and ignores canonical realization/csv-row choice (`project_artifact_handlers.py:148-203`, `205-215`).
5. Recommended storage: formalize canonical lexeme selection in `parse-enrichments.json` under `manual_overrides.canonical_lexemes`, not `survey-overlap.json`; add a focused API that validates bundle/speaker/csv-row membership and writes atomically.

## Verified data example

Workspace check against `/home/lucas/parse-workspace/concepts.csv` confirms the motivating case:

| csv row id | concept_en | source_survey | source_item |
|---:|---|---|---|
| 53 | `big (A)` | `KLQ` | `4.1` |
| 619 | `big (B)` | `KLQ` | `4.1` |
| 150 | `big (A)` | `JBIL` | `169` |

The same workspace has `Saha01.parse.json` concept intervals for csv row `53` with `text: "big"`, illustrating why display text and csv row identity must stay separate.

## Target model

### Terms

- **Bundle** = one logical concept, e.g. `big`. It maps to N csv row ids across surveys and variants. Today this must be derived from `concepts.csv.concept_en` after stripping variant suffixes; future-proof code should emit an explicit `bundle_id` in a backend compare payload.
- **Bucket** = one elicitation event, i.e. `(survey_id, source_item)`. Rows `53` and `619` are one bucket: `(klq, 4.1)`; row `150` is another bucket: `(jbil, 169)`.
- **Variant** = one csv row inside a bucket. A/B/C variants share the elicitation event but represent different lexical forms the speaker offered.
- **Per-speaker view** = the active bucket(s) for one speaker and bundle, resolved from MC-367's `speaker_concept_survey_links` first, then global `concept_survey_links`, then legacy csv columns / `speaker_choices` fallback.
- **Canonical lexeme** = one selected csv row per `(speaker, bundle)` for downstream NEXUS/BEAST2 and wordlist export. The UI can show all buckets and variants, but export reads one selected row.

### Existing data shapes and their target responsibility

| Shape | Current evidence | Target responsibility |
|---|---|---|
| `concepts.csv` rows | `_load_concept_row` resolves by exact row `id` (`project_config_handlers.py:457-470`); duplication rewrites `concept_en` and appends sibling rows without touching annotation text (`concepts_io.py:100-168`). | Source of csv row ids, labels, variant labels, legacy `source_survey/source_item` fallback. |
| Annotation JSON concept tier | `AnnotationInterval` has both `text` and optional `concept_id` (`src/api/types.ts:5-10`); speaker-form lookup already uses `concept_id` (`speakerForm.ts:101-113`). | Source of speaker-specific realization timing and lexical form via `concept_id`; never use `text` as identity. |
| `survey-overlap.json` | Default includes `concept_survey_links` and `speaker_choices` (`survey_overlap.py:46-53`); normalization persists only those two maps (`survey_overlap.py:116-132`). | Survey metadata and survey/bucket overrides only. MC-367 adds `speaker_concept_survey_links`; Compare consumes it. |
| `parse-enrichments.json` | Enrichment store deep-merges patches and POSTs `/api/enrichments` (`enrichmentStore.ts:46-55`, `enrichments-tags-notes-imports.ts:9-12`); Compare writes cognates/flags/canonical-realization indexes there (`ParseUI.tsx:359-414`). | Manual Compare decisions: cognate groups, flags, borrowing flags, notes, and the new canonical lexeme choices. |
| NEXUS export | Backend reads enrichments, uses manual cognate sets before auto sets, and emits matrix rows by speaker (`project_artifact_handlers.py:148-215`, `217-252`). | Must validate/read canonical lexeme choices and decide blank/auto-pick behavior before matrix generation. |

## Current-state audit by file

### Active runtime seam outside `src/components/compare/`

`src/ParseUI.tsx` is not under the requested directory, but it is the active Compare implementation and must be treated as authoritative context. It groups config concepts through `groupConceptEntries` only when `currentMode === 'compare'` (`ParseUI.tsx:919-925`), renders the current Compare speaker table in the `currentMode === 'compare'` branch (`ParseUI.tsx:1826-2253`), writes per-speaker cognate overrides (`ParseUI.tsx:359-390`), writes speaker flags (`ParseUI.tsx:397-407`), and writes index-based `manual_overrides.canonical_realizations` (`ParseUI.tsx:410-414`, `2092-2127`, `2164-2227`). Required change: extract this live Compare model into typed bundle/bucket helpers instead of relying on both `ParseUI.tsx` and the older modular shell to imply partial semantics.

### `src/components/compare/` source files

| File | What it does today | Wrongness vs target model | Required change |
|---|---|---|---|
| `BorrowingPanel.tsx` | Barrel re-export to `compare-panels/BorrowingPanel` (`BorrowingPanel.tsx:1`). | No direct model issue, but it hides that the modular panel consumes flat `activeConcept`. | Keep barrel; update target export once panel accepts `bundleId` / selected canonical row. |
| `CognateCell.tsx` | Renders per-speaker cognate group and similarity bar; click cycles group letters (`CognateCell.tsx:14-17`, `33-36`, `65-113`). | It operates at `(speaker, displayed concept)` only; no csv-row/bucket context. | Add optional canonical-row context in label/title or keep as bundle-level cognate only after canonical selection is separate. |
| `CognateControls.tsx` | Barrel re-export to modular cognate controls (`CognateControls.tsx:1-2`). | Same flat-concept caveat as the target file. | Keep; downstream props should move from concept id string to bundle id. |
| `CommentsImport.tsx` | Imports Audition comments for one selected speaker and reloads enrichments (`CommentsImport.tsx:13-34`, `59-84`). | Comments import can attach lexeme notes by speaker/concept but does not know bundle/bucket/canonical. | No redesign blocker; add docs/tests if canonical row affects imported note display. |
| `CompareMode.tsx` | Modular shell: loads enrichments/tags and switches between Cognate/Borrowing/Enrichments/Tags tabs (`CompareMode.tsx:16-43`, `99-141`). | Not the active `ParseUI` Compare table; it delegates to flat panels with no bundle/bucket contract. | Either retire or reconcile with active Compare by giving it the new compare-bundle API and route. |
| `ConceptTable.tsx` | Barrel re-export to modular table (`ConceptTable.tsx:1-2`). | The implementation underneath is flat. | Keep barrel; update target table after bundle/bucket table lands. |
| `ContactLexemePanel.tsx` | Displays CLEF provider coverage and starts/polls contact-lexeme fetch jobs (`ContactLexemePanel.tsx:7-17`, `40-55`, `90-117`). | CLEF coverage is concept-level and does not distinguish variants/buckets. | New Compare bundle payload should expose reference-form coverage per bundle and selected canonical row. |
| `EnrichmentsPanel.tsx` | Legacy/modular enrichment inspector: reads enrichment store, selected speakers/config, computes cognate/borrow/tag summaries, and exposes export/compute controls (`EnrichmentsPanel.tsx:60-68`, `80-91`, `122-167`, `216-266`). | It mixes `manual_overrides.cognate_sets` with flat active concept ids and has no canonical lexeme model. | Split into read-only summary vs canonical-edit surfaces; ensure export controls invoke canonical-aware NEXUS. |
| `LexemeDetail.tsx` | Barrel re-export to `compare-panels/LexemeDetail` (`LexemeDetail.tsx:1-2`). | Underlying component stores notes/tags by flat concept id. | Pass actual csv row id plus bundle id so notes remain lexeme-specific and canonical selection can point at the same row. |
| `ManageTagsView.tsx` | Standalone Tags mode UI over concepts/tags/speaker scope (`ManageTagsView.tsx:54-78`, `92-135`, `158-226`). | It types concepts with optional `sourceSurvey` but not buckets/variants (`ManageTagsView.tsx:16-42`). | Keep tags concept-scoped; when bundle model lands, tag application must resolve to all bundle row ids or explicit row ids. |
| `SpeakerImport.tsx` | Modal for onboarding speaker/audio/csv and polling import job (`SpeakerImport.tsx:12-23`, `38-71`, `98-123`). | No direct Compare data-model issue; import output seeds the annotation/concepts data the model consumes. | No MC-368 change except validation fixtures should include imported multi-row bundle cases. |
| `TagManager.tsx` | Modal tag manager using config concepts and selected speakers (`TagManager.tsx:21-40`, `40-62`, `94-140`, `215-298`). | Reads `config.concepts` into a flat list; cannot express bundle-wide vs row-specific tagging. | Either keep for legacy tags or update to show bundle rows and apply tags to row ids deliberately. |
| `UIPrimitives.tsx` | Dumb `Pill` and `SectionCard` UI wrappers (`UIPrimitives.tsx:3-20`). | No model issue. | Reuse for new Compare sections. |

### `src/components/compare/compare-panels/` files

| File | What it does today | Wrongness vs target model | Required change |
|---|---|---|---|
| `BorrowingClassifier.tsx` | Renders per-speaker borrowing radio controls and similarity accordion (`BorrowingClassifier.tsx:17-67`, `78-127`). | All callbacks are keyed by speaker and active concept only, not canonical row or bucket. | Keep decision UI but key borrowing flags by bundle + canonical row where appropriate. |
| `BorrowingPanel.tsx` | Uses `lookupForm`, similarity data, and `manual_overrides.borrowing_flags` to adjudicate borrowings (`BorrowingPanel.tsx:11-17`, `41-50`, `67-85`, `101-113`). | `lookupForm` inherits `lookupEntry` text matching; decisions store flat active concept. | Consume bundle candidate forms and write borrowing flags for the canonical lexeme/bundle. |
| `CognateActionMenu.tsx` | Button row for accept/merge/split/cycle modes (`CognateActionMenu.tsx:5-30`). | It changes group mode only; no canonical row control. | Retain as group action menu; add separate canonical radio/menu in table cells. |
| `CognateControls.tsx` | Hooks current active concept, speakers, enrichments, and `useCognateDecisions` to render speaker buttons (`CognateControls.tsx:8-13`, `58-85`). | Active concept is a string from `useUIStore`, not a bundle id with buckets/variants. | Accept `bundleId` and candidate speakers from compare-bundle model. |
| `ConceptRow.tsx` | Renders one concept row with one cell per speaker, looks up forms/cognate/tags, expands to lexeme detail (`ConceptRow.tsx:21-24`, `45-51`, `109-123`). | This is exactly the flat table that cannot show all survey buckets/variants. | Replace with `BundleRow` → `BucketGroup` → `VariantCandidate` hierarchy and per-speaker canonical picker. |
| `ConceptTable.tsx` | Parses `config.concepts`, renders `ConceptRow` for each concept, and uses speakers as columns (`ConceptTable.tsx:9-12`, `24-35`, `41-68`). | One row per concept and one column per speaker; no bundle/bucket/variant nesting. | Replace parser with backend/typed bundle payload; keep speaker columns only if each cell can expand across buckets. |
| `LexemeDetail.tsx` | Shows speaker lexeme note, audio/spectrogram controls, tags, and confirmed-anchor tag handling (`LexemeDetail.tsx:11-20`, `73-84`, `96-147`). | Notes and tags use a single `conceptId`; for bundle UI this can collapse different csv rows. | Pass `csvRowId` as lexeme id; display bundle id for context only. |
| `LexemeForm.tsx` | Stateless form for note/tag editing (`LexemeForm.tsx:4-35`, `64-124`). | No row-id distinction in props beyond `conceptId`. | Rename/extend `conceptId` prop to `csvRowId` or pass both. |
| `shared.ts` | Normalizes concepts, parses `config.concepts`, finds annotation entries, resolves cognate groups, normalizes borrowing decisions (`shared.ts:27-46`, `53-81`, `96-118`, `169-190`). | `lookupEntry` uses `iv.text` (`shared.ts:71`) and `parseConcepts` emits flat `{id,label,key}` (`shared.ts:35-46`). | Make row-id lookup mandatory via `iv.concept_id`; move bundle parsing out of `config.concepts` into a typed helper shared with active Compare. |
| `types.ts` | Local component types for forms, decisions, props, and rows (`types.ts:3-11`, `30-74`). | Types have no bundle, bucket, csv row id, survey override, or canonical selection structures. | Add `CompareBundle`, `CompareBucket`, `CompareVariant`, `CanonicalLexemeSelection` types in a shared lib/API file. |
| `useCognateDecisions.ts` | Manages local group state, saves `manual_overrides.cognate_sets`, handles accept/merge/split/cycle (`useCognateDecisions.ts:7-24`, `26-43`, `45-65`, `74-145`). | Saves by `activeConcept` only; speaker presence uses `speakerHasForm`, which inherits flat lookup. | Save groups by bundle id and decide whether group membership follows canonical lexeme or bundle-level speaker membership. |
| `useCompareSelection.ts` | Reads stores for config, annotation records, active concept, selected speakers, enrichments (`useCompareSelection.ts:6-23`). | Store selection has no bundle/csv-row distinction. | Return `activeBundle`, `activeRowId`, and resolved selected speaker set. |
| `useEnrichmentsBinding.ts` | Tiny enrichment store binding (`useEnrichmentsBinding.ts:3-6`). | No issue, but writes are currently broad deep-merge saves. | Reuse for UI optimism; backend canonical endpoint should validate/atomic-write. |
| `cluster-barrels.test.tsx` | Verifies barrels and compare-panel modules export the expected symbols (`cluster-barrels.test.tsx:4-18`, `25-35`). | Pins current module shape only. | Update when new bundle files/barrels are added. |

### Test files under `src/components/compare/`

| File | Current coverage | Gap to add in follow-up lanes |
|---|---|---|
| `BorrowingPanel.test.tsx` | Mocks active concept/speakers/enrichments and tests per-speaker borrowing decisions (`BorrowingPanel.test.tsx:20-45`, `152-211`). | Add bundle/canonical-row borrowing persistence tests. |
| `CognateCell.test.tsx` | Tests color mapping, click cycle, long-press reset (`CognateCell.test.tsx:35-67`). | Keep; add accessibility labels when canonical row context is displayed. |
| `CognateControls.test.tsx` | Tests merge/split/cycle against flat `cognate_sets` (`CognateControls.test.tsx:114-194`). | Rewrite to bundle-keyed cognate sets and canonical-row-aware speakers-with-form. |
| `CompareMode.test.tsx` | Tests modular shell hydration and tab switching (`CompareMode.test.tsx:81-112`). | Add integration tests only if modular shell remains active. |
| `ConceptTable.test.tsx` | Tests flat concept rows and note save using raw concept key (`ConceptTable.test.tsx:128-193`). | Add variant disambiguation, multi-bucket display, and per-speaker canonical picker tests. |
| `ContactLexemePanel.test.tsx` | Tests coverage rendering and fetch state (`ContactLexemePanel.test.tsx:44-67`). | Add provider coverage per bundle if backend payload changes. |
| `EnrichmentsPanel.test.tsx` | Tests placeholder/loading/cognate/export/compute/tag summaries (`EnrichmentsPanel.test.tsx:107-190`). | Add canonical summary/export readiness warnings. |
| `ManageTagsView.test.tsx` | Tests tag filtering/editing across concepts/speakers (`ManageTagsView.test.tsx:69-176`). | Add bundle-row tag semantics once decided. |
| `SpeakerImport.test.tsx` | Tests import form, polling, success/error states (`SpeakerImport.test.tsx:48-134`). | No direct change; add fixture-based compare tests elsewhere. |
| `TagManager.test.tsx` | Tests modal tag creation/editing/concept assignment (`TagManager.test.tsx:76-180`). | Update if TagManager moves from flat config concepts to bundle-aware concepts. |
| `UIPrimitives.test.tsx` | Tests primitive rendering (`UIPrimitives.test.tsx:33-38`). | No model change. |

## Findings

### Finding 1 — Modular Compare parses a flat concept list from `config.concepts`

File: `src/components/compare/compare-panels/shared.ts:35-46` and `ConceptTable.tsx:24` (`origin/main @ f861f4a`)

```ts
export function parseConcepts(concepts: unknown): { id: string; label: string; key?: string }[] {
  if (!Array.isArray(concepts)) return [];
  return concepts.map((c) => {
    if (typeof c === "string") {
      const id = normalizeConcept(c);
      return { id, label: c };
    }
```

Why wrong:
- The target model needs bundles, buckets, variants, and csv row ids; this function returns only flat concepts.
- It cannot distinguish `big (A)` row `53`, `big (B)` row `619`, and `big (A)` row `150` as one bundle with two buckets.

Fix shape:
- Replace `parseConcepts(config.concepts)` with a typed compare-bundle builder/API returning `{bundle_id, label, buckets[], row_ids[]}`.
- Tests: one bundle with KLQ A/B plus JBIL A; singleton fallback.

Estimated diff: ~220 LoC helper/API types + ~180 LoC tests.

### Finding 2 — Modular `lookupEntry` matches annotation intervals by `iv.text`, not `concept_id`

File: `src/components/compare/compare-panels/shared.ts:53-81` (`origin/main @ f861f4a`)

```ts
const conceptInterval = rec.tiers.concept.intervals.find((iv) => normalizeConcept(iv.text) === conceptId);
```

Why wrong:
- `text` is a denormalized display label; `concept_id` is the durable csv-row link (`AnnotationInterval` exposes both at `src/api/types.ts:5-10`).
- `duplicate_concept_variant` rewrites/appends `concepts.csv` rows (`python/concepts_io.py:145-158`) but does not migrate annotation interval `text` (`concepts_io.py:160-168`).
- Current workspace evidence has Saha01 intervals with `text: "big"` and `concept_id: "53"`; text cannot distinguish A/B/JBIL rows.

Fix shape:
- Change lookup to `String(iv.concept_id ?? '') === csvRowId` with a limited fallback for legacy no-`concept_id` intervals.
- Tests: concept interval text intentionally differs from csv row label; both variants share `text` but different `concept_id`.

Estimated diff: ~35 LoC implementation + ~80 LoC tests.

### Finding 3 — Modular `ConceptTable` is one row per concept and one column per speaker

File: `src/components/compare/compare-panels/ConceptTable.tsx:41-68` and `ConceptRow.tsx:45-51` (`origin/main @ f861f4a`)

```tsx
{concepts.map((concept, index) => (
  <ConceptRow key={concept.id} concept={concept} ... />
))}
```

Why wrong:
- It has no place to display multiple buckets under one bundle.
- It has no per-speaker canonical selector inside a speaker cell; each cell resolves one `lookupEntry(records, speaker, concept.id)`.

Fix shape:
- Replace with bundle rows. Each bundle row renders bucket headers `(survey, item)` and variant candidates. Each speaker cell exposes a canonical radio/menu for all candidate csv row ids.

Estimated diff: ~450 LoC UI + ~250 LoC tests if extracted from `ParseUI.tsx` instead of patched inline.

### Finding 4 — Active Compare has canonical-realization UI, but not canonical csv-row selection

Files: `src/ParseUI.tsx:410-414`, `2092-2127`, `2164-2227`; `src/lib/speakerForm.ts:225-268` (`origin/main @ f861f4a`)

```ts
const patch = { manual_overrides: { canonical_realizations: { [conceptForOverride.key]: { [speaker]: safeIdx } } } };
```

Why wrong / nuance:
- The background claim "no canonical-selection UI anywhere" is too broad on current main: active Compare does show realization pills/radios and writes `canonical_realizations`.
- But that store is keyed by displayed `concept.key` and an integer `idx`. It does not say which csv row id was chosen, which survey bucket it came from, or whether it should drive NEXUS.
- `speakerForm.ts` maps variants to realizations by current concept shape, not a full bundle across all surveys (`speakerForm.ts:251-268`).

Fix shape:
- Migrate from `canonical_realizations[bundleOrConceptKey][speaker] = idx` to `canonical_lexemes[bundle_id][speaker] = {csv_row_id, survey_id, source_item, realization_index}`.
- Preserve `canonical_realizations` only as a migration seed/fallback.

Estimated diff: ~160 LoC FE migration/read path + ~140 LoC tests.

### Finding 5 — `survey-overlap.json` is not yet speaker-row override capable on `origin/main`

Files: `python/survey_overlap.py:46-53`, `116-132`, `160-191`; `src/api/types.ts:171-188` (`origin/main @ f861f4a`)

Current state includes:

```py
"concept_survey_links": {},
"speaker_choices": {},
```

and TypeScript mirrors only:

```ts
export type SpeakerSurveyChoices = Record<string, Record<string, string>>;
```

Why wrong:
- MC-368 needs per-speaker csv-row survey links (`speaker_concept_survey_links`) to resolve which bucket is active for one speaker without rewriting global links.
- Repo-wide search on this baseline returned zero `speaker_concept_survey_links` matches, so Compare cannot consume it until MC-367 lands.

Fix shape:
- Depend on MC-367's storage/API shape; do not introduce a parallel compare-only survey override store.
- Compare should read `speaker_concept_survey_links[speaker][csv_row_id]` before global `concept_survey_links[csv_row_id]`.

Estimated diff belongs to MC-367; MC-368 consumption ~100 LoC selector tests.

### Finding 6 — NEXUS export ignores canonical lexeme choices

File: `python/app/http/project_artifact_handlers.py:148-215` (`origin/main @ f861f4a`)

```py
for key in union_keys:
    override_block = override_sets.get(key)
    auto_block = auto_sets.get(key)
    block = override_block if isinstance(override_block, dict) else auto_block
```

Why wrong:
- Export only knows cognate-set membership by concept key and speaker. It never reads `canonical_realizations` or a csv-row canonical choice.
- The produced matrix answers "is speaker in group X for concept key Y?" but not "which lexical row did this speaker contribute for bundle Y?"

Fix shape:
- Load canonical lexeme choices before matrix construction.
- For each `(speaker, bundle)`, decide selected csv row by explicit canonical choice; if absent, follow Lucas's answer to the blank-vs-auto-pick open question.
- Export warnings should include missing/invalid canonical row counts.

Estimated diff: ~180 LoC backend export + ~160 LoC tests.

### Finding 7 — Save/Load Decisions omits current canonical-realization data

File: `src/lib/decisionPersistence.ts:18-23`, `95-107`, `131-138`, `173-191` (`origin/main @ f861f4a`)

```ts
export interface CanonicalDecisionManualOverrides {
  cognate_decisions: CognateDecisionMap;
  cognate_sets: CognateSetMap;
  speaker_flags: SpeakerFlagMap;
  borrowing_flags: BorrowingFlagMap;
}
```

Why wrong:
- Even the existing `canonical_realizations` manual override cannot round-trip through decision export/import.
- New canonical lexeme choices must be part of this decision payload if Lucas expects Save/Load Decisions to preserve Compare review state.

Fix shape:
- Extend decision payload to include `canonical_lexemes` and a migration reader for legacy `canonical_realizations`.

Estimated diff: ~90 LoC + ~80 LoC tests.

### Finding 8 — Current grouping is bucket-based, not bundle-based

File: `src/lib/conceptGrouping.ts:95-160` (`origin/main @ f861f4a`)

```ts
const bucketKey = sourceBucketKey(sourceItem, entry.source_survey);
const siblings = sourceBuckets.get(bucketKey) ?? [];
```

Why wrong:
- This correctly groups variants that share `(source_survey, source_item)` but does not group all buckets under one logical bundle.
- The target needs `big` → buckets `{KLQ/4.1, JBIL/169}` → variants `{53,619,150}`.

Fix shape:
- Keep bucket grouping as an inner layer; add bundle grouping above it by normalized concept stem / backend bundle id.

Estimated diff: ~180 LoC model helper + ~180 LoC tests.

## Proposed canonical-selection storage

### Recommendation

Extend `parse-enrichments.json`, not `survey-overlap.json`, with a formal manual override:

```json
{
  "manual_overrides": {
    "canonical_lexemes": {
      "bundle:big": {
        "Saha01": {
          "csv_row_id": "53",
          "survey_id": "klq",
          "source_item": "4.1",
          "bucket_key": "klq\u00004.1",
          "realization_index": 0,
          "selected_at": "2026-05-11T00:00:00Z",
          "source": "manual"
        }
      }
    }
  }
}
```

Why this location:
- Compare already stores manual review state in enrichments (`manual_overrides.cognate_sets`, `speaker_flags`, `canonical_realizations`) (`ParseUI.tsx:359-414`).
- NEXUS export already reads `parse-enrichments.json` (`project_artifact_handlers.py:148-153`).
- `survey-overlap.json` should remain survey/bucket metadata; canonical lexeme choice is an analysis/review decision, not survey configuration.

### API proposal

Add focused endpoints instead of relying only on broad `/api/enrichments` POST:

- `GET /api/compare/bundles?speaker=Saha01` → returns bundle payload with buckets, variants, resolved speaker links, existing canonical selection, and validation warnings.
- `PUT /api/compare/canonical-lexemes/{bundleId}/{speaker}` with body:
  ```json
  {
    "csv_row_id": "53",
    "realization_index": 0
  }
  ```
- Response returns the updated canonical selection and the normalized bundle row.

Validation:
- `bundleId` must exist in current concepts payload.
- `csv_row_id` must be a row in that bundle.
- If `realization_index` is present, it must be in range for that speaker/row's discovered realizations.
- If MC-367 per-speaker survey links exist, selected row must still be visible; if not visible, return `409` with a repair hint.

Atomicity:
- Current server `_write_json_file` writes directly (`server.py:417-422`), while `survey_overlap.save_survey_overlap_state` uses temp + `os.replace` (`survey_overlap.py:150-157`). The canonical endpoint should use the latter pattern for `parse-enrichments.json` writes.

### Migration plan

1. On read, if `manual_overrides.canonical_lexemes` is absent but `manual_overrides.canonical_realizations` exists, map indexes onto the current bundle's ordered variants when unambiguous (`ParseUI.tsx:410-414`, `speakerForm.ts:251-268`). Mark `source: "migration:canonical_realizations"`.
2. Do **not** seed canonical lexeme from `cognate_sets` automatically unless Lucas approves; group membership only says cognate class, not which A/B/JBIL lexeme is selected.
3. If no explicit selection and Lucas chooses auto-pick, store no row until user clicks; compute an ephemeral `effective_canonical` with `source: "default:first-visible"` so data files distinguish defaults from human review.

## Proposed Compare UI

### Shape

Keep Compare reachable from the existing Compare table, but change the body from:

```text
Concept row → speaker columns → one IPA/cognate/flag cell
```

to:

```text
Bundle row: big
  Bucket: KLQ · 4.1
    Variant A · row 53  | Saha01 [radio canonical] /ipa/ "orth" | Khan02 ...
    Variant B · row 619 | Saha01 [radio]           /ipa/ "orth" | Khan02 ...
  Bucket: JBIL · 169
    Variant A · row 150 | Saha01 [radio]           /ipa/ "orth" | Khan02 ...
```

### Pseudocode

```tsx
<BundleRow bundle={bundle}>
  {bundle.buckets.map(bucket => (
    <BucketSection key={bucket.bucketKey} survey={bucket.surveyId} item={bucket.sourceItem}>
      {bucket.variants.map(variant => (
        <VariantRow key={variant.csvRowId}>
          {speakers.map(speaker => (
            <CanonicalLexemeCell
              bundleId={bundle.bundleId}
              speaker={speaker}
              csvRowId={variant.csvRowId}
              candidate={bundle.candidates[speaker]?.[variant.csvRowId]}
              checked={canonical[bundle.bundleId]?.[speaker]?.csv_row_id === variant.csvRowId}
              onChange={() => saveCanonical(bundle.bundleId, speaker, variant.csvRowId)}
            />
          ))}
        </VariantRow>
      ))}
    </BucketSection>
  ))}
</BundleRow>
```

NEXUS export pulls selections from `manual_overrides.canonical_lexemes`; if missing, it follows Lucas's blank-vs-auto-pick policy and reports warnings.

## Follow-up implementation lanes

### Proposed lane 1 — BE compare-bundle payload + canonical storage/API

Goal: Add a backend compare-bundle model and canonical lexeme API that consumes MC-367's `speaker_concept_survey_links`.

Files / estimates:
- `python/compare_bundles.py` (new): ~260 LoC
- `python/server_routes/compare.py`: ~110 LoC
- `python/app/http/project_artifact_handlers.py`: ~180 LoC
- `python/external_api/openapi.py`: ~90 LoC
- `python/test_compare_bundles.py` (new): ~280 LoC
- `python/test_app_http_project_artifact_handlers.py`: ~120 LoC

Acceptance:
- `GET /api/compare/bundles` returns bundle → buckets → variants for the `big` case.
- `PUT /api/compare/canonical-lexemes/{bundleId}/{speaker}` validates row membership and writes atomically.
- NEXUS export reads canonical choices and reports missing/invalid choices.
- Tests cover MC-367 per-speaker override precedence.

Dependencies: MC-367-A storage shape merged.
LoC estimate: ~1,040.

### Proposed lane 2 — FE compare model/types/selectors

Goal: Add typed frontend helpers/API contracts for bundle/bucket/variant/canonical selection without rewriting the visual table yet.

Files / estimates:
- `src/api/types.ts`: ~90 LoC
- `src/api/contracts/compare.ts` (new): ~90 LoC
- `src/lib/compareBundles.ts` (new): ~260 LoC
- `src/lib/__tests__/compareBundles.test.ts` (new): ~300 LoC
- `src/stores/enrichmentStore.ts`: ~40 LoC if optimistic canonical patch helper is added

Acceptance:
- FE can load and normalize backend bundle payload.
- Selector resolves canonical candidate per `(bundle,speaker)` with explicit/missing/invalid states.
- Tests cover multiple buckets, A/B variants, MC-367 speaker override, and missing `concept_id` fallback warning.

Dependencies: Lane 1 API contract, MC-367-B type additions if already present.
LoC estimate: ~780.

### Proposed lane 3 — FE Compare table redesign

Goal: Replace the active Compare speaker-form table with a bundle/bucket/variant table and per-speaker canonical controls.

Files / estimates:
- `src/ParseUI.tsx`: net -250 LoC if extracted / +80 LoC wiring
- `src/components/compare/CompareBundleTable.tsx` (new): ~420 LoC
- `src/components/compare/CanonicalLexemeCell.tsx` (new): ~180 LoC
- `src/components/compare/CognateCell.tsx`: ~40 LoC
- `src/lib/speakerForm.ts`: ~160 LoC
- `src/ParseUI.test.tsx` and/or new component tests: ~420 LoC

Acceptance:
- Existing Compare route remains reachable.
- For `big`, all KLQ/JBIL buckets and A/B variants are visible.
- User can choose one canonical csv row per speaker per bundle.
- Save updates backend canonical endpoint and reload preserves selection.
- Existing cognate/flag/notes controls still work.

Dependencies: Lane 1 and Lane 2.
LoC estimate: ~1,300.

### Proposed lane 4 — Decision export/import + legacy modular cleanup

Goal: Ensure Save/Load Decisions and modular `compare-panels` do not silently drop canonical selections.

Files / estimates:
- `src/lib/decisionPersistence.ts`: ~140 LoC
- `src/lib/decisionPersistence.test.ts`: ~180 LoC
- `src/components/compare/compare-panels/*`: ~160 LoC if kept in sync; otherwise remove/deprecate unused shell after verifying routes
- `src/components/compare/compare-panels/cluster-barrels.test.tsx`: ~40 LoC

Acceptance:
- `parse-decisions.json` includes `canonical_lexemes`.
- Import preserves existing cognate/flag/borrowing data and canonical choices.
- Modular shell either consumes bundle model or is explicitly retired to avoid dual semantics.

Dependencies: Lane 2 canonical types; can land before Lane 3 if schema is stable.
LoC estimate: ~520.

## Open questions for Lucas

1. Should **no canonical chosen yet** produce a blank NEXUS cell / warning, or auto-pick the first visible variant?
2. When per-speaker survey overrides disagree — e.g. `speaker_concept_survey_links`, older `speaker_choices`, and global `concept_survey_links` point to different buckets — what is the precedence? Proposed: `speaker_concept_survey_links` → `speaker_choices` → global/legacy.
3. Should migration seed `canonical_lexemes` from existing `canonical_realizations` automatically when row ordering is unambiguous?
4. Should migration ever seed from `cognate_sets`, or should cognate grouping remain independent from canonical lexeme choice?
5. What is the durable `bundle_id` policy: normalized gloss label (`bundle:big`), backend-generated stable id, or sorted row-id hash? Proposed beta: backend emits deterministic normalized gloss with collision suffix and includes `row_ids` for repair.
6. If a speaker has data for KLQ but an override selects JBIL with no annotation interval, should UI allow selecting that row as blank, or hide it as unavailable?
7. Should `parse-decisions.json` include canonical lexemes immediately, even before NEXUS consumes them, to preserve review work across branches?

## Validation expectations for follow-up lanes

- Backend lanes: `PYTHONPATH=python python3 -m pytest ...`, `uvx ruff check python/ --select E9,F63,F7,F82`, OpenAPI surface tests.
- Frontend lanes: `npx vitest run`, `./node_modules/.bin/tsc --noEmit`, `npm run build`.
- Integration: fixture with rows `53/619/150`, one speaker with only row `53`, one with multiple row ids, and one with no explicit canonical selection.
