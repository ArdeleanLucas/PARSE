# Compare-mode display bugs — empirical confirmation

**Date:** 2026-05-19
**Reporter:** Lucas (concepts "big" Saha01/Fail01, "bird" all speakers)
**Repo state:** `main` @ `66d33f03`
**Workspace state:** `/home/lucas/parse-workspace` on PC, same date

Three independent bugs in Compare mode that all surface as "the collapsed row IPA and the expanded variant card disagree, or one of them is empty/wrong." Confirmed with failing vitest tests in [src/lib/__tests__/compareDisplayBugs.test.ts](../../src/lib/__tests__/compareDisplayBugs.test.ts).

---

## Bug 1 — Saha01 "big": collapsed IPA cell ≠ expanded variant card

### Symptom

Concept "big", Saha01 row: collapsed cell shows `/enemfuːikalaŋpi/`, but expanding the row shows the only variant card as `/goːrɔ/` ("A", canonical). Both purport to be Saha01's "big" form.

### Saved data

Saha01.parse.json has two concept intervals on `concept_id=53` ("big (A)" KLQ 4.1), and two IPA intervals overlapping them — of different durations:

| concept interval | IPA interval | duration |
|---|---|---|
| `[4013.131, 4013.999]` text="big (A)" | `[4013.131, 4013.999]` text=`ɡoːrɔ` | 0.868 s |
| `[4024.0, 4025.051]` text="big" | `[4024.0, 4025.051]` text=`enemfuːikalaŋpi` | 1.051 s |

Verified: **no** IPA intervals in Saha01.parse.json carry a `concept_id` field (0 of 499). Same for Fail01 (0 of 453). The backend's "match siblings by cid" path is therefore inert; it always falls through to time-overlap.

### Root cause — two algorithms, same data

**Frontend** (collapsed cell at [src/components/compare/SpeakerFormsTable.tsx:1034-1036](../../src/components/compare/SpeakerFormsTable.tsx)) reads `form.ipa`, built by `buildSingleRealizationForVariant` which collects **all** overlapping IPA intervals across **all** concept intervals on that cid and picks the **longest**:

```ts
// src/lib/speakerForm.ts:123-131
function buildSingleRealizationForVariant(
  record: AnnotationRecord | null | undefined,
  conceptKey: string,
): Realization {
  const variantConceptIntervals = conceptIntervalsForKey(record, conceptKey);
  const variantIpaIntervals = ipaIntervalsForConceptIntervals(record, variantConceptIntervals);
  const longest = pickLongestInterval(variantIpaIntervals);
  return longest ? realizationFromIpaInterval(record, longest) : emptyRealization();
}
```

**Backend** (variant card at [src/components/compare/SpeakerFormsTable.tsx:654](../../src/components/compare/SpeakerFormsTable.tsx) reads `bundle.candidates[speaker][csv_row_id].ipa`) takes **only the first** concept interval and picks its **nearest-start** IPA:

```python
# python/compare_bundles.py:358-376
if matches:
    concept_interval = matches[0]
    cid = _interval_concept_id(concept_interval)
    ipa_interval = (
        _pick_sibling(ipa_by_concept.get(cid, []), tiers["ipa"], concept_interval, 0)
        if cid
        else None
    )
    speaker_candidates[row_id] = _candidate_from_interval(
        concept_interval,
        source_wav,
        ortho_interval=ortho_interval,
        ipa_interval=ipa_interval,
        ...
    )
```

```python
# python/compare_bundles.py:146-170
def _pick_time_overlap(candidates, concept_interval):
    overlapping = [c for c in candidates if _overlap_seconds(c, concept_interval) > 0]
    if not overlapping:
        return None
    concept_start = _seconds(concept_interval.get("start") ...)
    return min(overlapping, key=lambda c: abs(_seconds(c.get("start") ...) - concept_start))

def _pick_sibling(siblings_for_cid, all_siblings, concept_interval, concept_index):
    if 0 <= concept_index < len(siblings_for_cid):
        return siblings_for_cid[concept_index]
    return _pick_time_overlap(all_siblings, concept_interval)
```

For Saha01's data: frontend picks `enemfuːikalaŋpi` (longer); backend picks `ɡoːrɔ` (nearest to `matches[0].start = 4013.131`).

### Failing test

```ts
it('form.ipa for a grouped concept should equal the backend candidate ipa', () => {
  const bigConcept: Concept = {
    id: 1, key: '4.1', name: 'big', tag: 'untagged',
    sourceItem: '4.1', sourceSurvey: 'KLQ',
    variants: [
      { conceptKey: '53',  conceptEn: 'big (A)', variantLabel: 'A' },
      { conceptKey: '619', conceptEn: 'big (B)', variantLabel: 'B' },
    ],
  };
  const record = makeRecord({
    concept: [
      { start: 4013.131, end: 4013.999, text: 'big (A)', concept_id: '53' },
      { start: 4024.0,   end: 4025.051, text: 'big',     concept_id: '53' },
    ],
    ipa: [
      { start: 4013.131, end: 4013.999, text: 'ɡoːrɔ' },
      { start: 4024.0,   end: 4025.051, text: 'enemfuːikalaŋpi' },
    ],
  });
  const backendCandidateIpa = 'ɡoːrɔ';
  const form = buildSpeakerForm(record, bigConcept, 'Saha01', {}, false, []);
  expect(form.ipa).toBe(backendCandidateIpa);
});
```

**Result on `main` @ 66d33f03:**

```
AssertionError: expected 'enemfuːikalaŋpi' to be 'ɡoːrɔ' // Object.is equality
- Expected
+ Received
- ɡoːrɔ
+ enemfuːikalaŋpi
 ❯ src/lib/__tests__/compareDisplayBugs.test.ts:87:22
```

---

## Bug 2 — Fail01 "big": empty IPA despite real annotation data

### Symptom

Concept "big", Fail01 row: collapsed cell shows `—`. But in Annotate mode at 58:12.30, Fail01 has IPA `gap` / ortho `گاپ` saved on this concept.

### Saved data

Fail01.parse.json has two concept intervals **on `concept_id=634`** ("big" plain, KLQ 4.1) — **not** on 53 or 150 ("big (A)"):

| concept interval | text | audition_prefix | overlapping ipa |
|---|---|---|---|
| `[3492.305, 3493.186]` | "big" | "169" (JBIL) | `ɡap` |
| `[7571.15,  7571.91]`  | "big" | "4.1" (KLQ)  | (none) |

In the React Concept object, the grouped "big" concept (`key="4.1"`, `sourceItem="4.1"`) has variants in this order:

```
[ 53 (A),  619 (B),  620 (C),  621 (D),  631 (E),  634 (—),  664 (F) ]
                                                   ^^^
                                          Fail01's data is here
```

### Root cause — `selectedIdx` defaults to 0

`buildSpeakerForm` builds one realization per variant. For Fail01:

```
realizations = [ {}, {}, {}, {}, {}, { ipa: 'ɡap', ortho: 'گەپ', … }, {} ]
                  ^                          ^
                  index 0                    index 5  ← real data
```

```ts
// src/lib/speakerForm.ts:274-294 — source-item branch
if (concept.sourceItem && concept.variants && concept.variants.length >= 2) {
  const realizations = concept.variants.map((variant) => buildSingleRealizationForVariant(record, variant.conceptKey));
  const selectedIdx = readCanonicalOverride(canonicalOverrides, concept.key, speaker, realizations.length);
  const canonical = realizations[selectedIdx];
  return {
    ...,
    ipa: canonical?.ipa ?? '',
    ...
  };
}
```

```ts
// src/lib/speakerForm.ts:133-146
function readCanonicalOverride(canonicalOverrides, overrideKey, speaker, realizationCount): number {
  if (realizationCount <= 0) return 0;
  const conceptCanonical = canonicalOverrides && isRecord(canonicalOverrides[overrideKey])
    ? canonicalOverrides[overrideKey] as Record<string, unknown>
    : null;
  const rawIdx = conceptCanonical?.[speaker];
  const requestedIdx = typeof rawIdx === 'number' && Number.isInteger(rawIdx) && rawIdx >= 0 ? rawIdx : 0;
  return Math.min(requestedIdx, realizationCount - 1);
}
```

With no canonical override `selectedIdx = 0`, so `canonical = realizations[0] = {}` and `form.ipa = ''`. Collapsed cell renders `—`.

The backend handles this correctly with a "default:single-candidate" auto-pick when exactly one row has a candidate:

```python
# python/compare_bundles.py:389-390
if effective is None and len(candidate_rows) == 1:
    effective = _selection_for_row(bundle, candidate_rows[0], source="default:single-candidate", realization_index=0)
```

The frontend `buildSpeakerForm` has no equivalent.

### Failing test

```ts
it('auto-selects the only non-empty realization when there is no canonical override', () => {
  const bigConcept: Concept = {
    id: 1, key: '4.1', name: 'big', tag: 'untagged',
    sourceItem: '4.1', sourceSurvey: 'KLQ',
    variants: [
      { conceptKey: '53',  conceptEn: 'big (A)', variantLabel: 'A' },
      { conceptKey: '619', conceptEn: 'big (B)', variantLabel: 'B' },
      { conceptKey: '634', conceptEn: 'big',     variantLabel: ''  },
    ],
  };
  const record = makeRecord({
    concept:     [{ start: 3492.305, end: 3493.186, text: 'big',  concept_id: '634' }],
    ipa:         [{ start: 3492.305, end: 3493.186, text: 'ɡap' }],
    ortho_words: [{ start: 3492.305, end: 3493.186, text: 'گەپ' }],
  });
  const form = buildSpeakerForm(record, bigConcept, 'Fail01', {}, false, []);
  expect(form.realizations[2]).toMatchObject({ ipa: 'ɡap' });
  expect(form.realizations[0]).toMatchObject({ ipa: '' });
  expect(form.ipa).toBe('ɡap');
  expect(form.selectedIdx).toBe(2);
});
```

**Result on `main` @ 66d33f03:**

```
AssertionError: expected '' to be 'ɡap' // Object.is equality
- Expected
+ Received
- ɡap
 ❯ src/lib/__tests__/compareDisplayBugs.test.ts:137:22
```

---

## Bug 3 — "bird" displays the "yellow" bundle (sourceItem ⊠ row_id collision)

### Symptom

Concept "bird" in Compare. Collapsed IPAs look right (e.g. Fail01 `/paranda/`, Saha01 `/plebar/`, Khan02 `/teːr/`). Every speaker's **expanded** panel shows yellow data — Fail01's canonical card is `/zart/` زرد, Khan02's two cards are `/zert/` and `/zertçør/`, audio links to yellow's `start_sec/end_sec`, and the Metadata block reads:

```
Bundle           bundle:yellow
Active bucket    JBIL · 178
Variants         1
```

…on the bird concept.

### Saved data

`concepts.csv`:

```
id=92   concept_en='yellow'      source_item=5.5  source_survey=KLQ
id=167  concept_en='yellow (A)'  source_item=178  source_survey=JBIL
id=311  concept_en='bird (A)'    source_item=92   source_survey=JBIL
id=651  concept_en='bird (B)'    source_item=92   source_survey=JBIL
```

The string `"92"` is **a csv row id** for yellow **and** **a source_item** for bird.

### Root cause — namespaces conflated in `findBundleForConcept`

Frontend grouping ([src/lib/conceptGrouping.ts:30-38, 159-169](../../src/lib/conceptGrouping.ts)) names a grouped concept by its `sourceItem`:

```ts
function groupedConceptKey(
  sourceItem: string,
  sourceSurvey: string | undefined,
  sourceItemsWithMultipleGroupedBuckets: ReadonlySet<string>,
): string {
  if (!sourceItemsWithMultipleGroupedBuckets.has(sourceItem)) return sourceItem;
  const survey = normalizeSourceSurvey(sourceSurvey) ?? 'unspecified';
  return `source:${survey}:${sourceItem}`;
}
```

→ The grouped "bird" concept gets `concept.key = "92"`.

The backend bundles label rows by their csv id:

```
bundle:bird   row_ids = ["311", "651"]
bundle:yellow row_ids = ["92",  "167"]
```

Then [src/lib/compareBundles.ts:138-151](../../src/lib/compareBundles.ts) matches `concept.key` against `bundle.row_ids` literally — **mixing the two namespaces**:

```ts
export function findBundleForConcept(
  bundles: readonly CompareBundle[],
  concept: { key: string; name: string },
): CompareBundle | null {
  const conceptKey = cleanString(concept.key);
  if (conceptKey) {
    const byRowId = bundles.find((bundle) => bundle.row_ids.some((rowId) => cleanString(rowId) === conceptKey));
    if (byRowId) return byRowId;
  }

  const conceptLabel = cleanString(concept.name).toLocaleLowerCase();
  if (!conceptLabel) return null;
  return bundles.find((bundle) => cleanString(bundle.label).toLocaleLowerCase() === conceptLabel) ?? null;
}
```

For the bird concept: `concept.key === "92"` ⇒ `bundle.row_ids.includes("92")` ⇒ returns **bundle:yellow**. The label fallback that would have matched `"bird" === "bird"` is never reached.

The "big" concept escapes this trap only because `"4.1"` doesn't appear as a csv row id anywhere.

### Failing test

```ts
const bundleYellow: CompareBundle = {
  bundle_id: 'bundle:yellow', label: 'yellow', row_ids: ['92', '167'],
  buckets: [
    { bucket_key: 'klq 5.5',  survey_id: 'klq',  source_item: '5.5', variants: [{ csv_row_id: '92',  variant_label: '',  label: 'yellow' }] },
    { bucket_key: 'jbil 178', survey_id: 'jbil', source_item: '178', variants: [{ csv_row_id: '167', variant_label: 'A', label: 'yellow (A)' }] },
  ],
};
const bundleBird: CompareBundle = {
  bundle_id: 'bundle:bird', label: 'bird', row_ids: ['311', '651'],
  buckets: [{
    bucket_key: 'jbil 92', survey_id: 'jbil', source_item: '92',
    variants: [
      { csv_row_id: '311', variant_label: 'A', label: 'bird (A)' },
      { csv_row_id: '651', variant_label: 'B', label: 'bird (B)' },
    ],
  }],
};

it('returns bundle:bird, not bundle:yellow, for the grouped bird concept', () => {
  const birdConcept = { key: '92', name: 'bird' };
  expect(findBundleForConcept([bundleYellow, bundleBird], birdConcept)?.bundle_id).toBe('bundle:bird');
});
```

**Result on `main` @ 66d33f03:**

```
AssertionError: expected 'bundle:yellow' to be 'bundle:bird' // Object.is equality
- Expected
+ Received
- bundle:bird
+ bundle:yellow
 ❯ src/lib/__tests__/compareDisplayBugs.test.ts:201:86
```

---

## Full vitest summary

```
 RUN  v1.6.1 /home/lucas/gh/tarahassistant/PARSE-rebuild

 ❯ src/lib/__tests__/compareDisplayBugs.test.ts  (3 tests | 3 failed) 6ms
   ❯ Bug 1 — collapsed IPA cell vs expanded variant card (Saha01 "big") > form.ipa for a grouped concept should equal the backend candidate ipa
     → expected 'enemfuːikalaŋpi' to be 'ɡoːrɔ'
   ❯ Bug 2 — empty form.ipa when only a non-zero variant has data (Fail01 "big") > auto-selects the only non-empty realization when there is no canonical override
     → expected '' to be 'ɡap'
   ❯ Bug 3 — findBundleForConcept collides sourceItem with csv row id (bird/yellow) > returns bundle:bird, not bundle:yellow, for the grouped bird concept
     → expected 'bundle:yellow' to be 'bundle:bird'

 Test Files  1 failed (1)
      Tests  3 failed (3)
```

---

## Fix sketch

Three independent root causes → three independent fixes. Suggested grouping for an MC parent task:

| # | File | Fix |
|---|---|---|
| 1 | [src/components/compare/SpeakerFormsTable.tsx](../../src/components/compare/SpeakerFormsTable.tsx) **or** [src/lib/speakerForm.ts](../../src/lib/speakerForm.ts) | Either (A) render collapsed cell from `bundle.candidates` instead of `form.ipa`, or (B) make `buildSingleRealizationForVariant` mirror `_pick_sibling` (first concept interval, nearest-start IPA). |
| 2 | [src/lib/speakerForm.ts:276,299](../../src/lib/speakerForm.ts) | When no canonical override and exactly one realization has IPA/ortho data, set `selectedIdx` to that index. Mirrors backend `default:single-candidate`. |
| 3 | [src/lib/compareBundles.ts:138-151](../../src/lib/compareBundles.ts) | In `findBundleForConcept`: when `concept.variants` is non-empty, match by `variant.conceptKey` (guaranteed csv-row-id namespace) instead of `concept.key`. Fall back to label match. |

Tests in [src/lib/__tests__/compareDisplayBugs.test.ts](../../src/lib/__tests__/compareDisplayBugs.test.ts) will go green when each lane lands.
