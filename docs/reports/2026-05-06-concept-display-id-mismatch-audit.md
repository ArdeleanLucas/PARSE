# Concept display-id / raw concept-id mismatch audit

Date: 2026-05-06
Scope: PARSE frontend concept lookup against live workspace data under `/home/lucas/parse-workspace`.

## Summary

The raw saved annotation data is not what is causing the `long`/`salt` examples to appear at the wrong times. The primary bug is a frontend identity mismatch:

- `src/lib/conceptGrouping.ts` emits grouped display concepts with new sequential `Concept.id` values.
- `src/lib/parseUIUtils.ts::conceptMatchesIntervalText()` and `src/components/annotate/annotate-views/shared.ts::findAnnotationForConcept()` then compare annotation `interval.concept_id` against that display id.
- The annotation files store raw `concepts.csv` ids, not display ids.

Once concept grouping collapses any duplicate `source_item`, every subsequent display id can drift away from its raw concept id. In this workspace, the first drift occurs at displayed row `27`: frontend display `wife of brother` intends raw key(s) `28`, but lookup uses raw id `27` (`brother of husband (B)`).

## Severity

🔴 High. Annotate/Compare can show, seek, save, and reason over the wrong concept interval while displaying a different concept label. This is a silent UI data-contract bug, not a cosmetic label issue.

## Audit results

- Grouped display rows whose `Concept.id` no longer names their raw concept key(s): **496**.
- Active wrong display lookups found across speaker annotation files: **3024** speaker/concept rows.
- Full machine-readable audit: [`2026-05-06-concept-display-id-mismatch-audit.tsv`](./2026-05-06-concept-display-id-mismatch-audit.tsv)

### Affected rows by speaker

| Speaker | concept intervals | rows where current frontend lookup can select the wrong raw interval |
|---|---:|---:|
| Fail01 | 523 | 411 |
| Khan02 | 503 | 406 |
| Qasr01 | 506 | 405 |
| Kalh01 | 543 | 404 |
| Saha01 | 497 | 392 |
| Mand01 | 519 | 387 |
| Khan01 | 286 | 258 |
| Khan03 | 283 | 258 |
| Fail02 | 131 | 103 |
| Khan04 | 138 | 0 |

## User-reported examples: Saha01

These confirm Lucas's observation: the saved data says the timestamps belong to different concepts, while the frontend display lookup attaches them to shifted labels.

| Display id used by frontend | Displayed concept | Intended raw key(s) | Raw concept actually matched by current lookup | First matched time | Saved text at matched interval | Audition prefix | Intended intervals present? |
|---:|---|---|---|---|---|---|---:|
| 50 | salt KLQ 3.14 | 52 | 50 God KLQ 3.11 | 9116.0-9116.878 | God | 3.11 | 0 |
| 51 | big KLQ 4.1 | 53 | 51 hill KLQ 3.13 | 9148.329-9148.771999999999 | hill | 3.13 | 2 |
| 53 | long KLQ 4.3 | 55 | 53 big KLQ 4.1 | 4013.131-4013.999 | big | 169 | 0 |

Concrete source-data evidence for the two examples:

- `Saha01.json` at `4013.131-4013.999` has `concept_id: "53"`, `text: "big"`, `audition_prefix: "169"`.
- `audio/original/Saha01/Sahana_F_1978_01 - Kaso Solav.csv` has `169- big A` at `1:06:53.131`.
- `Saha01.json` at `9116.000-9116.878` has `concept_id: "50"`, `text: "God"`, `audition_prefix: "3.11"`.
- `audio/original/Saha01/Sahana_F_1978_01 - Kaso Solav.csv` has `(3.11)- God` at `2:31:56.000`.

Therefore:

- Displayed `long` KLQ `4.3` is intending raw concept `55`, but current lookup uses display id `53`, which is raw `big` KLQ `4.1`.
- Displayed `salt` KLQ `3.14` is intending raw concept `52`, but current lookup uses display id `50`, which is raw `God` KLQ `3.11`.

## Most common wrong display mappings observed

| Affected speakers | Displayed concept | Raw concept matched by current lookup |
|---:|---|---|
| 8 | sixteen (16) | one (1) |
| 8 | seventeen (17) | two (2) |
| 8 | eighteen (18) | three (3) |
| 8 | nineteen (19) | four (4) |
| 8 | twenty (20) | five (5) |
| 8 | twenty (21) | six (6) |
| 8 | thirty (22) | seven (7) |
| 8 | forty (23) | eight (8) |
| 8 | fifty (24) | nine (9) |
| 8 | seventy (26) | eleven (11) |
| 8 | eighty (27) | twelve (12) |
| 8 | ninety (28) | thirteen (13) |
| 8 | one hundred (29) | fourteen (14) |
| 8 | two hundred (30) | fifteen (15) |
| 8 | head (31) | sixteen (16) |
| 8 | hair ( (32) | seventeen (17) |
| 8 | eye (33) | eighteen (18) |
| 8 | ear (35) | nineteen (19) |
| 8 | mouth (36) | twenty (20) |
| 8 | tongue (38) | thirty (22) |

## Representative examples

| Speaker | Display id | Displayed concept | Raw concept matched by current lookup | First matched time | Saved text | Intended interval count |
|---|---:|---|---|---|---|---:|
| Fail01 | 28 | sister of husband KLQ 2.17 | 28 wife of brother KLQ 2.16 | 6309.546-6310.469 | wife of brother | 1 |
| Fail01 | 29 | brother of wife KLQ 2.18 | 29 sister of husband KLQ 2.17 | 6329.0-6329.71 | sister of husband | 1 |
| Fail01 | 30 | sister of wife KLQ 2.19 | 30 brother of wife KLQ 2.18 | 6526.599-6527.678 | brother of wife | 1 |
| Fail01 | 31 | son of sister KLQ 2.20 | 31 sister of wife KLQ 2.19 | 6558.111-6559.439 | sister of wife | 1 |
| Fail01 | 32 | daughter of sister KLQ 2.21 | 32 son of sister KLQ 2.20 | 6572.097-6572.999 | son of sister | 1 |
| Fail01 | 33 | son of brother KLQ 2.22 | 33 daughter of sister KLQ 2.21 | 6580.0-6580.924 | daughter of sister | 1 |
| Fail01 | 34 | daughter of brother KLQ 2.23 | 34 son of brother KLQ 2.22 | 6598.0-6599.0 | son of brother | 1 |
| Fail01 | 35 | step-father KLQ 2.24 | 35 daughter of brother KLQ 2.23 | 6600.6-6601.371 | daughter of brother | 1 |
| Fail01 | 36 | step-mother KLQ 2.25 | 36 step-father KLQ 2.24 | 6626.293-6627.371999999999 | step-father | 1 |
| Fail01 | 37 | step-son KLQ 2.26 | 37 step-mother KLQ 2.25 | 6634.422-6635.522 | step-mother | 1 |
| Fail01 | 38 | step-daughter KLQ 2.27 | 38 step-son KLQ 2.26 | 6647.902-6648.847 | step-son | 1 |
| Fail01 | 39 | child of one’s daughter KLQ 2.28 | 39 step-daughter KLQ 2.27 | 6750.073-6751.152 | step-daughter | 1 |
| Fail01 | 40 | child of one’s son KLQ 2.29 | 40 child of one’s daughter KLQ 2.28 | 6790.208-6791.245999999999 | child of one’s daughter | 1 |
| Fail01 | 41 | rain KLQ 3.1 | 41 child of one’s son KLQ 2.29 | 6913.131-6914.097000000001 | child of one’s son | 2 |
| Fail01 | 42 | thunder KLQ 3.2 | 42 rain KLQ 3.1 | 6920.704-6921.608 | rain | 1 |
| Fail01 | 43 | snow KLQ 3.4 | 43 thunder KLQ 3.2 | 6928.268-6929.491 | thunder | 3 |
| Fail01 | 44 | ice JBIL 123 | 44 snow KLQ 3.4 | 6947.129-6948.208 | snow | 1 |
| Fail01 | 45 | hail KLQ 3.6 | 45 ice JBIL 123 | 1942.897-1943.769 | ice | 1 |
| Fail01 | 48 | God KLQ 3.11 | 48 wind KLQ 3.7 | 6965.681-6966.585 | wind | 1 |
| Fail01 | 49 | hill KLQ 3.13 | 49 shade KLQ 3.10 | 7002.529-7003.649 | shade | 1 |
| Fail01 | 50 | salt KLQ 3.14 | 50 God KLQ 3.11 | 7013.405-7014.237 | God | 1 |
| Fail01 | 51 | big KLQ 4.1 | 51 hill KLQ 3.13 | 7043.819-7044.999000000001 | hill | 2 |
| Fail01 | 52 | small KLQ 4.2 | 52 salt KLQ 3.14 | 7055.204-7055.999 | salt | 2 |
| Fail01 | 53 | long KLQ 4.3 | 53 big KLQ 4.1 | 7063.663-7064.423 | big | 1 |
| Fail01 | 54 | short KLQ 4.4 | 54 small KLQ 4.2 | 7065.678-7066.346 | small | 1 |
| Fail01 | 55 | high KLQ 4.5 | 55 long KLQ 4.3 | 7068.661-7069.411 | long | 1 |
| Fail01 | 56 | low (wall) KLQ 4.6 | 56 short KLQ 4.4 | 7071.293-7072.074 | short | 1 |
| Fail01 | 57 | wide (road) KLQ 4.7 | 57 high KLQ 4.5 | 7076.564-7077.314 | high | 1 |
| Fail01 | 58 | narrow (road) KLQ 4.8 | 58 low (wall) KLQ 4.6 | 7091.388-7092.241 | low (wall) | 1 |
| Fail01 | 59 | fat (man) KLQ 4.9 | 59 wide (road) KLQ 4.7 | 7098.803-7099.584 | wide (road) | 1 |

## Root-cause code path

1. `/api/config` exposes raw concepts from `concepts.csv` as `{ id, label, source_item, source_survey }`.
2. `src/lib/conceptGrouping.ts::groupConceptEntries()` rewrites those into display concepts with fresh sequential numeric ids.
3. `src/lib/parseUIUtils.ts::conceptMatchesIntervalText()` treats `concept.id` as an identity key:

```ts
return intervalConceptId != null && intervalConceptId !== "" && String(intervalConceptId) === String(concept.id);
```

4. `src/components/annotate/annotate-views/shared.ts::findAnnotationForConcept()` and `src/ParseUI.tsx` use that predicate to choose annotation intervals.
5. Annotation records store raw ids from `concepts.csv` in `interval.concept_id`.

The contract breach is that `Concept.id` is a display-order id after grouping, while `interval.concept_id` is a raw data id.

## Write-path risk

The same identity mismatch can affect explicit Annotate writes, but the observed risk shape is slightly different from simple “new rows use display ids”. Current `AnnotateView` Save Annotation / quick-retime calls `saveLexemeAnnotation()` with only timestamp bounds and `conceptName`, not a `concept_id` parameter. The store then:

1. locates the concept interval by `oldStart` / `oldEnd`, where those bounds came from the already-wrong read-side lookup;
2. retimes that raw interval in place;
3. overwrites its `text` with the displayed concept name; and
4. preserves the existing raw `concept_id` because `updateMatchingInterval()` spreads the old interval.

So for the reported `long` example, saving while the UI is on displayed `long` would target the raw `big` interval (`concept_id: "53"`) and can rewrite its text/times as if it were `long`. That is worse than a label-only display bug: the UI can persist wrong `text` and retiming edits onto the wrong raw concept row. It does not appear, from this path, to persist a brand-new concept-tier interval with the grouped display id; instead it mutates the wrong existing raw-id interval selected by the read bug. Any eventual fix should still audit all write paths and tests for both cases:

- no use of grouped display ids when creating or updating `concept_id` fields;
- no mutation of a wrong raw interval due to a read-side lookup that already selected the wrong bounds.

Related paths that already use raw `concept.key` for sidecar metadata look safer on first inspection: speaker notes (`saveLexemeNote({ concept_id: concept.key })`), concept tags, and confirmed anchors are keyed by `concept.key`. This audit did not exhaustively certify generic interval editing APIs or backend compute refresh targets.

## Fix direction

Frontend concept lookup and write targeting should match against raw concept keys, not grouped display ids.

Likely implementation shape:

- Introduce a helper that extracts all raw keys represented by a display concept:
  - `concept.key`
  - `concept.variants[].conceptKey`
  - `concept.mergedKeys`
  - `concept.mergedVariants[].conceptKey` if needed
- Replace `conceptMatchesIntervalText(concept, interval.concept_id)` with raw-key membership.
- Keep annotation matching identity-only; do not fall back to text labels.
- Add regressions proving a grouped/variant source-item row does not shift later KLQ rows:
  - displayed `salt` must not match raw `God`
  - displayed `long` must not match raw `big`
  - displayed `big` must match raw `big`

## Additional review gaps / follow-up audit notes

### Existing on-disk text mismatch scan

A quick concept-tier scan now checks every active `/home/lucas/parse-workspace/annotations/*.json` file for rows where `interval.concept_id` resolves through raw `concepts.csv`, but `interval.text` does not exactly equal the raw concept name. Full output: [`2026-05-06-concept-tier-text-mismatch-audit.tsv`](./2026-05-06-concept-tier-text-mismatch-audit.tsv).

Results:

- **275** exact mismatch rows across active annotation JSON files.
- Deduplicating `.json` / `.parse.json` mirror rows by speaker/timing/identity/text gives **166** distinct mismatch rows.
- Many are expected label-normalization variants (`nose` vs `nose (A)`, `grass` vs `grass A`, possessive prompts like `my son` vs `son`). After a simple suffix/variant normalization, **115** file rows / **78** distinct rows remain suspicious.
- Only **1** suspicious normalized mismatch is currently marked `manuallyAdjusted: true`: `Saha01.parse.json` has `concept_id: "50"` resolving to raw `God` (`KLQ 3.11`) at `9116.0-9116.878`, but `text: "salt"`. This is exactly the kind of already-on-disk mutation the write-path risk predicts.

By distinct speaker rows after simple normalization:

| Speaker | exact text mismatches | suspicious normalized mismatches | manually-adjusted suspicious mismatches |
|---|---:|---:|---:|
| Khan01 | 39 | 13 | 0 |
| Khan02 | 93 | 52 | 0 |
| Khan03 | 33 | 12 | 0 |
| Saha01 | 1 | 1 | 1 |

This is not yet a full corruption classifier: Khan legacy data has many import-label quirks, so mismatch rows require manual classification before any repair. But it gives the missing “already on disk” risk number and identifies the strongest UI-induced candidate.

### Backend/compute scoped-refresh risk

The frontend scoped-refresh path deserves audit before any eventual fix lands. `useParseUIPipeline()` accepts backend `affected_concepts` / `affectedConcepts` and `ParseUI.tsx` forwards them to `useAnnotationStore.getState().applyConceptScopedRefresh()`. In `src/stores/annotation/actions.ts`, `targetId()` resolves `target.concept_id ?? target.conceptId ?? target.id`, and `intervalMatchesTarget()` compares that id against interval `id`, `concept_id`, `conceptId`, then positional fallback.

Current risk framing: if those targets are emitted by backend code using raw ids, this path is compatible. If any frontend or backend caller ever passes a grouped display `Concept.id` as `id` / `conceptId`, scoped refresh can reproduce the same identity drift and patch the wrong row. The eventual implementation PR should trace every `affected_concepts` producer and pin regression coverage for raw-id-only targets.

### Compare write paths

This audit walked Annotate writes in detail, but Compare has separate state writes:

- Compare flag/accept buttons in `ParseUI.tsx` use `concept.key`, so concept tags appear raw-keyed and safer on first inspection.
- Compare notes persistence currently uses `persistCompareNotes(conceptId, value)` where `conceptId` is the grouped display id. That is localStorage UI state rather than annotation JSON, but it can still drift notes across grouped concept rows and should be migrated/audited with the read-side fix.
- `AIChat` receives `conceptId={concept.id}` in Compare; chat is maintenance-only, but any tool call or context that treats that id as a raw concept id is suspect.

## Data caveat

This audit is about frontend lookup and write-risk triage. It does not certify every raw annotation interval as linguistically correct. It does show that the specific `long`/`salt` wrong-time behavior, and many similar rows, are explainable by frontend id drift rather than by originally corrupted timestamps in the saved annotation files; the added mismatch scan shows at least one likely already-persisted text mutation (`Saha01.parse.json`, raw `God` row now texted `salt`).
