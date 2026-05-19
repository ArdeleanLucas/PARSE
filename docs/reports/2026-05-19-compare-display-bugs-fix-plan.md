# Compare-mode display bugs — fix plan

**Companion to:** [`docs/reports/2026-05-19-compare-display-bugs.md`](./2026-05-19-compare-display-bugs.md) (bug report) and the failing tests in `src/lib/__tests__/compareDisplayBugs.test.ts`.

**Dependency:** issue [#529](https://github.com/ArdeleanLucas/PARSE/issues/529) — concept identity pollution. This plan assumes #529's data-model migration lands. Empirically simulated against the live workspace `/home/lucas/parse-workspace`:

```
concepts.csv: 666 rows
merge_map: 97 non-canonical ids re-keyed
post-#529 row count: 569

big after #529:   id=53  KLQ 4.1  + id=150 JBIL 169  (was: 53 619 620 621 631 634 664 / 150)
bird after #529:  id=311 JBIL 92                     (was: 311 / 651)
yellow after #529: id=92 KLQ 5.5 + id=167 JBIL 178   (unchanged)

Fail01 'big' tags after re-keying: cid=634 -> cid=53 (both intervals)
Saha01 'big' tags after re-keying: cid=53 / cid=631 -> cid=53 (all three intervals)
```

---

## Resolution matrix

| Bug | Resolved by #529? | Why |
|---|---|---|
| **Bug 1** — Saha01 collapsed `/enemfuːikalaŋpi/` ≠ expanded `/ɡoːrɔ/` | ✅ **Yes (for the reported scenario)** | "big" becomes a singleton, removing the `sourceItem + variants ≥ 2` branch that called `pickLongestInterval`. Default branch picks `realizations[0]` (first IPA in tier order) — matches backend `_pick_time_overlap(matches[0])`. |
| **Bug 2** — Fail01 collapsed `—` despite annotated `ɡap` | ✅ **Yes (fully)** | Pure data-shape issue. Fail01's intervals on `cid=634` re-key to `cid=53`; concept becomes a singleton; default branch `matchingIpaIntervals` finds the IPA. `selectedIdx=0` is no longer wrong because index 0 IS the data. |
| **Bug 3** — bird concept renders bundle:yellow data | ⚠️ **Partial — needs explicit fix** | The bird-specific case is incidentally fixed (bird becomes a singleton). But the underlying collision in `findBundleForConcept` persists for **14 other grouped buckets** that survive #529 (clarifier-suffix concepts sharing a slot). |

**Recommendation: total fix for Bug 3 in this PR. Bug 1 and Bug 2 ride #529.**

---

## Why Bug 3 still needs a code fix

`#529` merges only rows that share `(source_survey, source_item, base_label)`. Rows that share `(source_survey, source_item)` but have **different base_labels** (clarifier suffixes like `(collective)`, `(men)`, `(women)`, `(organ)`) **remain grouped** in the frontend's `conceptGrouping.ts`. There are **30** such residual buckets after #529, and **14 of them have a `source_item` that also exists as a csv row id** — exactly the namespace collision Bug 3 describes.

Empirical sample from `/home/lucas/parse-workspace` post-#529:

```
bucket=(JBIL,123)  siblings=[('45','ice'),('144','snow')]
   sourceItem '123' is csv row id for bundle 'to jump'
   findBundleForConcept(key="123", name="ice") -> bundle:to-jump  ← wrong

bucket=(JBIL,75)   siblings=[('138','sister'),('612','sister B'),('613','sister A')]
   sourceItem '75' is csv row id for bundle 'thirsty'
   findBundleForConcept(key="75", name="sister") -> bundle:thirsty  ← wrong

bucket=(JBIL,319)  siblings=[('517','I'),('558','i am teaching'),('592','i saw you'),
                              ('593','i see you'),('601','Im a teacher')]
   sourceItem '319' is csv row id for bundle 'wood (substance)'
   findBundleForConcept(key="319", name="I") -> bundle:wood-substance  ← wrong

… 11 more buckets, including (JBIL,32) hair (men)/(women), (JBIL,48) stomach (organ)
```

These are sentence-tier and clarifier-tier concepts. Users opening any of them in Compare will get the wrong bundle's candidates rendered for every speaker. The bird case was just the first one Lucas found.

---

## The total fix for Bug 3

### Location

[`src/lib/compareBundles.ts:138-151`](../../src/lib/compareBundles.ts)

### Current code

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

### Proposed code

```ts
import type { Concept } from './speakerForm';

export function findBundleForConcept(
  bundles: readonly CompareBundle[],
  concept: { key: string; name: string; variants?: readonly { conceptKey: string }[]; mergedKeys?: readonly string[] },
): CompareBundle | null {
  // Match using csv-row-id values, never `concept.key` directly — grouped
  // concepts use `sourceItem` (e.g. "92", "319") as their key and that
  // shares a namespace with csv row ids, causing wrong-bundle matches
  // when the sourceItem string happens to equal an unrelated row id.
  const rowIdCandidates: string[] = [];
  if (concept.mergedKeys?.length) rowIdCandidates.push(...concept.mergedKeys.map(cleanString).filter(Boolean));
  if (concept.variants?.length) rowIdCandidates.push(...concept.variants.map((v) => cleanString(v.conceptKey)).filter(Boolean));
  if (rowIdCandidates.length === 0) rowIdCandidates.push(cleanString(concept.key));

  for (const rowId of rowIdCandidates) {
    if (!rowId) continue;
    const byRowId = bundles.find((bundle) => bundle.row_ids.includes(rowId));
    if (byRowId) return byRowId;
  }

  const conceptLabel = cleanString(concept.name).toLocaleLowerCase();
  if (!conceptLabel) return null;
  return bundles.find((bundle) => cleanString(bundle.label).toLocaleLowerCase() === conceptLabel) ?? null;
}
```

### Why this works

- **Grouped concept** (e.g. `(JBIL, 123)` with siblings `ice` + `snow`): `concept.variants` exists with `conceptKey` values `"45"` and `"144"` (real csv row ids). The matcher tries `bundle.row_ids.includes("45")` → bundle:ice; or `…includes("144")` → bundle:snow. Either way, never bundle:to-jump (which owns row_id `"123"`).
- **User-merged concept**: `concept.mergedKeys` is populated with the underlying csv row ids. Same path.
- **Singleton concept** (post-#529 most concepts): no variants, no mergedKeys → `concept.key` itself is already a csv row id ([`conceptGrouping.ts:81-93`](../../src/lib/conceptGrouping.ts)). Falls through to the same lookup that exists today.
- **Pre-#529 dataset**: same behaviour, because pre-#529 grouped concepts also expose `variants[*].conceptKey`. The fix is forward- and backward-compatible.

### Tests

- The existing failing test in `src/lib/__tests__/compareDisplayBugs.test.ts` (Bug 3) goes green.
- Add a regression test using one of the 14 residual buckets — e.g. the `(JBIL,123)` ice/snow case — so post-#529 grouped concepts are covered:

```ts
it('routes a grouped clarifier-suffix concept to its own bundle (post-#529 residual case)', () => {
  // (JBIL, 123) clusters 'ice' (id 45) and 'snow' (id 144) at a slot where
  // sourceItem "123" is also a csv row id for an unrelated concept.
  const bundleIce: CompareBundle = {
    bundle_id: 'bundle:ice', label: 'ice', row_ids: ['45'],
    buckets: [{ bucket_key: 'jbil 123', survey_id: 'jbil', source_item: '123', variants: [{ csv_row_id: '45', label: 'ice' }] }],
  };
  const bundleToJump: CompareBundle = {
    bundle_id: 'bundle:to-jump', label: 'to jump', row_ids: ['123'],
    buckets: [{ bucket_key: 'klq …', survey_id: 'klq', source_item: '…', variants: [{ csv_row_id: '123', label: 'to jump' }] }],
  };
  const iceGrouped = {
    key: '123', name: 'ice',
    variants: [{ conceptKey: '45' }, { conceptKey: '144' }],
  };
  expect(findBundleForConcept([bundleToJump, bundleIce], iceGrouped)?.bundle_id).toBe('bundle:ice');
});
```

- Update the existing test at [`src/lib/__tests__/compareBundles.test.ts:104-108`](../../src/lib/__tests__/compareBundles.test.ts) — `"matches singleton concepts by row id before considering labels"` still passes (singleton path unchanged), but worth a comment that the row-id match is now gated on missing variants/mergedKeys.

### Risk

Low. Three call sites for `findBundleForConcept` (`ParseUI.tsx`); all pass a `Concept` object that already carries `variants` and `mergedKeys`. No backend coordination. No data migration. Pure frontend.

---

## Why Bug 1 rides #529

Pre-#529 trace, "big" Saha01:

```
concept = {key:"4.1", sourceItem:"4.1", variants:[53,619,...,664]}  ← grouped
  -> buildSpeakerForm takes sourceItem branch (line 274-294)
  -> buildSingleRealizationForVariant("53") -> pickLongestInterval -> enemfuːikalaŋpi
backend candidate.ipa for row 53 -> _pick_time_overlap(matches[0]) -> ɡoːrɔ
collapsed /enemfuːikalaŋpi/  vs  expanded /ɡoːrɔ/   ← bug
```

Post-#529 trace, same speaker:

```
concept = {key:"53", sourceItem:"4.1"}  ← singleton (only canonical row in KLQ-4.1 bucket)
  -> buildSpeakerForm sourceItem branch SKIPPED (variants undefined, length < 2)
  -> default branch (line 297): realizations = matchingIpaIntervals.map(...)
  -> matchingIpaIntervals in tier order: [ɡoːrɔ@4013, enemfuːikalaŋpi@4024, bikalan@4025.5]
  -> selectedIdx = 0 -> form.ipa = ɡoːrɔ
backend candidate.ipa for row 53 -> _pick_time_overlap(matches[0]=[4013,4014]) -> ɡoːrɔ
collapsed /ɡoːrɔ/  ===  expanded /ɡoːrɔ/   ✓
```

The algorithmic divergence (`pickLongestInterval` vs nearest-start) **still exists in code**, but the call path that triggered it is no longer reached for "big". It does still apply to the 30 residual grouped buckets post-#529 — but those are clarifier-suffix concepts, not common enough to be worth a coupled fix.

**Action:** none in this PR. File a follow-up to align `buildSingleRealizationForVariant` with backend semantics — low priority, latent.

## Why Bug 2 rides #529

Pre-#529: Fail01's `ɡap` is tagged on `cid=634` (variant index 5 of grouped "big"). `selectedIdx` defaults to 0; `realizations[0]` (cid=53) is empty; `form.ipa = ''`.

Post-#529: `cid=634` re-keys to `cid=53`. "big" is a singleton. Default branch:

```
matchingIpaIntervals (Fail01, cid=53) = [{ipa:'ɡap', start:3492.305, end:3493.186}]
realizations = [{ipa:'ɡap', ...}]
selectedIdx = 0 -> form.ipa = 'ɡap'   ✓
```

Pure data fix. No compare-mode code change needed.

**Action:** none in this PR.

---

## Sequencing

```
┌──────────────────────────────────────────────────────────┐
│  Now                                                     │
│  - Ship Bug 3 fix (this PR)                              │
│    - Total: 1 file changed (compareBundles.ts), ~15 LoC  │
│    - 2 tests: Bug 3 + new residual-case regression       │
│    - No data migration, no backend coordination          │
├──────────────────────────────────────────────────────────┤
│  Downstream (#529 lands)                                 │
│  - Bug 1 reported scenario auto-resolved                 │
│  - Bug 2 fully auto-resolved                             │
│  - Verify by re-running compareDisplayBugs.test.ts:      │
│    * Bug 1 test will need updating (post-#529 the        │
│      sourceItem-branch trigger no longer fires for       │
│      "big"). Rewrite as default-branch test that         │
│      asserts form.ipa == backend candidate.ipa for a     │
│      singleton with multi-interval data.                 │
│    * Bug 2 test will pass as-is (the assertion is        │
│      "form.ipa = 'ɡap'", and post-#529 it will be).      │
├──────────────────────────────────────────────────────────┤
│  Optional follow-up (low priority)                       │
│  - Align buildSingleRealizationForVariant with backend   │
│    _pick_time_overlap semantics. Closes the latent       │
│    Bug 1 pattern for the 30 residual grouped buckets.    │
└──────────────────────────────────────────────────────────┘
```

---

## Summary

- **Total fix in this PR:** Bug 3. `findBundleForConcept` matches by `variant.conceptKey` / `mergedKeys` before falling back to `concept.key`. ~15 LoC + 2 tests in [`src/lib/compareBundles.ts`](../../src/lib/compareBundles.ts) and [`src/lib/__tests__/compareDisplayBugs.test.ts`](../../src/lib/__tests__/compareDisplayBugs.test.ts).
- **Partial / downstream:** Bug 1 and Bug 2 resolve when #529 lands; no compare-mode changes needed for the reported scenarios. Latent Bug 1 pattern in residual grouped buckets is filed as low-priority follow-up.
