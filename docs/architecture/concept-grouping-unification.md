# Concept grouping unification (MC-458)

**Status:** design / research — proposes the long-term fix for how PARSE decides
"which concept rows are the same concept," and the migration to get there.

**Audience:** anyone touching Compare bundles, the Annotate concept list, or the
survey-overlap link layer.

---

## 1. The problem in one sentence

PARSE answers the question *"are these two `concepts.csv` rows the same concept?"*
in **three different places, three different ways**, none of which is the
authoritative one — and the module that was built to *be* authoritative has zero
consumers.

The visible symptoms are display bugs (a concept showing an A/B variant that does
not exist in Annotate; a bundle fusing unrelated glosses). The root is
architectural: **concept identity is computed ad-hoc and divergently instead of
once, from a single source of truth.**

---

## 2. The three grouping engines

| Engine | File | Merges two rows when… | Override layer | Validation | Warnings | Consumed by |
|---|---|---|---|---|---|---|
| **A — Identity module** | `python/concept_identity.py` | one row's **explicit cross-survey link** resolves to the other row's `(survey, item)` identity (transitive closure) | ✅ `concept-identity.json` — `manual:split` / `manual:merge`, stable `uid` | partial (orphans, uid collisions) | ✅ structured | **nobody (0 consumers)** |
| **B — Compare grouper** | `python/compare_bundles.py` (union-find) | **same stem** OR **shared `(survey, item)` pair** (legacy CSV + sidecar) | ❌ | ❌ | only legacy-text fallback | **Compare (`/api/compare/bundles`)** |
| **C — Annotate grouper** | `src/lib/conceptGrouping.ts` | **same `(source_survey, source_item)`** + frontend `conceptMerges` | FE merges only | ❌ | ❌ | **Annotate concept list** |

Engine **A** — closure + linguist override + stable `uid` + a warnings channel,
with a design doc (`concept-identity.md`) and 11 tests — is the intended source
of truth. It is **not wired in**. Compare runs **B**, Annotate runs **C**, and
the two reconcile only through `findBundleForConcept()`
(`src/lib/compareBundles.ts`), a bridge that exists *solely* to paper over the
row-id / source-item namespace mismatch between B and C.

### Why B and C diverge

- **B merges by English stem.** `"rain"` and `"rain"` merge because their gloss
  text matches — regardless of links. This is **gloss-as-identity**: it
  over-merges homonyms and, worse, lets one bad link cascade across every
  same-gloss row (see §4).
- **B merges by bare shared `(survey, item)`**, including a row's *own* legacy
  columns. A non-reciprocal link — row X declaring "I am also survey S item I"
  when row Y legitimately owns `(S, I)` — fuses X and Y with **no check that X
  and Y are the same concept**.
- **A merges only on explicit links** (the design's paradigm rule: a shared
  `source_item` is *not* an identity edge — one survey item can host a pronoun
  paradigm). No stem merge. So A never over-merges by gloss and never amplifies.
- **C groups by `(survey, source_item)`** on the frontend, producing keys like
  `source:JBIL:92` that collide with raw csv row ids — the reason
  `findBundleForConcept()` has to disambiguate.

---

## 3. Data flow today (current state)

```
 INPUTS (workspace sidecars, each keyed differently)
 ┌────────────────────────────────────────────────────────────────────────────┐
 │ concepts.csv          id, concept_en, source_survey, source_item, order      │
 │ survey-overlap.json   concept_survey_links{id:{survey:item}} (+ speaker_*)    │
 │ annotations/*.parse.json   tiers.concept[].concept_id → ipa/ortho tiers       │
 │ parse-enrichments.json     cognate_sets / canonical / flags / notes  (by id)  │
 │ concept-identity.json      uid → member rows, origin=auto|split|merge         │
 └────────────────────────────────────────────────────────────────────────────┘
        │                          │                                  │
   ┌────▼─────────────┐   ┌────────▼──────────────┐       ┌───────────▼───────────┐
   │  ENGINE C        │   │  ENGINE B             │       │  ENGINE A             │
   │ conceptGrouping  │   │ compare_bundles       │       │ concept_identity      │
   │  .ts (frontend)  │   │  union-find (backend) │       │  closure + override   │
   │                  │   │                       │       │                       │
   │ group by         │   │ MERGE IF:             │       │ MERGE IF:             │
   │ (survey,item)    │   │  A) same STEM   ◄─────────────┼─ amplifier            │
   │ + FE merges      │   │  B) shared (survey,   │       │  explicit link ONLY   │
   │                  │   │     item) pair        │       │  (no stem, no bare    │
   │                  │   │  non-reciprocal,      │       │   shared item)        │
   │                  │   │  no gloss check       │       │ + split/merge override│
   │                  │   │                       │       │ + warnings + uid      │
   └────────┬─────────┘   └───────────┬───────────┘       └──────────┬────────────┘
            │                         │                              │
       ANNOTATE list            /api/compare/bundles             (unused)
       "N OF 564"               buckets + candidates
            │                         │
            └──── findBundleForConcept() bridge ── reconciles by csv_row_id
                  (exists only because C ≠ B)
```

Three engines, two live and divergent, the correct one dark.

### Compare's grouping pipeline (Engine B), grounded

`python/compare_bundles.py::build_compare_bundles`:

| Stage | Lines (approx) | What it does |
|---|---|---|
| Row ingestion | filter for `id`+`concept_en` | `read_concepts_csv_rows` |
| **Union-find grouping** | `~323–365` | `_union`/`_find`; merge on **stem** (`stem_rep`) **and** `(survey,item)` **pair** (`pair_rep`, from `concept_survey_links_for_row` = legacy + sidecar) |
| Group label | `~378–383` | prefer clean gloss, shortest, lowest id |
| Bucket build | `~393–405` | per-row `_active_links` → `(survey,item)` buckets |
| Candidate build | `~431–496` | `by_concept[concept_id]` match; `legacy_by_text` stem fallback; realizations; `_pick_sibling` |
| Output | `~406–430` | `{bundle_id, label, row_ids, buckets, candidates, canonical, warnings, …}` |

Two properties make Engine B fragile, both confirmed in code:

1. **The stem merge** (`~352–357`) is a gloss-text identity edge — homonym
   over-merge and the transitive amplifier.
2. **The pair merge** (`~358–365`) is non-reciprocal and gloss-blind — any row
   that names a `(survey, item)` is unioned with whatever else names it, with no
   check the rows are the same concept.

A third, smaller hazard: the candidate matcher's `legacy_by_text` fallback
(`~448`) matches annotation intervals by **stem text** when no `concept_id`
matches — the same gloss-as-identity anti-pattern, able to pull an unrelated
interval.

---

## 4. How one bad link becomes a catastrophe (worked example)

Data fact: a single wrong link, `concept_survey_links["537"] = {jbil: "125"}` —
a *fog* row (KLQ 3.9) pointed at *rain* (JBIL 125, row 142); it should point at
the *fog* JBIL item (124, row 148). One off-by-one.

```
 rows:  42 rain(KLQ3.1)  616 rain(JBIL126)  142 rain(JBIL125)  148 fog(JBIL124)  537 fog(KLQ3.9)
 links: 42 ↔ 616 (good)                      (none)            (none)            537 → jbil:125 ⚠ BAD

 B-pair:  42 — 616        share klq:3.1 / jbil:126        ✓ correct
 B-pair:  142 — 537       537's bad link names jbil:125, 142 owns it    ✗ fog↔rain
 B-stem:  42 — 142 — 616  all gloss "rain"                ← amplifier step 1
 B-stem:  148 — 537       all gloss "fog"                 ← amplifier step 2

 closure ⇒  { 42, 142, 148, 537, 616 }  →  ONE "bundle:fog"
```

A speaker's *rain* form and *fog* form now sit in one bundle and render as A/B of
one lexeme. Annotate (Engine C, grouping by `(survey,item)`) never merges them,
so there it is correctly two concepts — **that divergence is the user-visible
bug.**

Note Engine A would make the *same* `{537,142}` merge from the same bad link (the
link is genuinely wrong) — but **only those two rows** (no stem cascade), and it
would surface a warning and offer a durable `manual:split`. The blast radius
difference (2 vs 5 rows) and the silence are the architectural failures.

---

## 5. The signal we were missing (link sweep)

A sweep of `concept_survey_links` against the example corpus (97 link entries)
classifies every link by whether its target `(survey, item)` is owned by a row
with a *matching* gloss:

- **Gloss-mismatch links (genuinely suspect):** a small set where a concept's
  link lands on an unrelated concept's item — e.g. *fog*→*rain*, *snow*→*ice*
  (and the reverse), plus pronoun→sentence links from a systematic import error.
- **Dangling links:** a handful pointing at `(survey, item)` pairs **no row
  owns** (stale references).
- **Cosmetic / clarifier variants (legitimate):** the large majority — `"salt"`
  / `"salt (eating)"`, `"green"` / `"green (grass)"`, `"twenty-one"` /
  `"twenty one"`, `"step-son"` / `"step-son \"son of husband\""`, sentence ± `!`.
  These **must not** be flagged.

Two design conclusions fall straight out of this data:

1. **Auto-deciding is unsafe.** Hard-blocking gloss-mismatch merges would
   correctly separate fog/rain and snow/ice but would *wrongly* split ~10
   legitimate clarifier variants. Removing the stem merge entirely splits ~7
   bundles *and* leaves fog/rain partly fused. **Neither is a safe automatic
   fix** — which is precisely why identity needs a *human override* layer, not a
   cleverer heuristic.
2. **A conservative warning is high-value and safe.** A heuristic that ignores
   identical / substring / clarifier / punctuation differences and flags only
   canonical-form divergence with low token overlap pinpoints the suspect links
   (fog/rain, snow/ice, …) with **zero** false positives on clarifier variants.

Conclusion (2) is shipped in **MC-458-B** as a behavior-preserving warning into
each bundle's existing `warnings` panel. It changes no grouping; it makes bad
links visible. It is the first, safe step of this plan.

---

## 6. Target architecture

**Principle: English gloss text is not identity. Identity is the explicit-link
closure, corrected by a human, addressed by a stable `uid`.** That is exactly
`concept_identity.py`. So:

```
            concepts.csv ─┐
       survey-overlap.json ┼──►  concept_identity.load()  ──►  ConceptIdentity
       concept-identity.json┘        (closure + override)        { uid → member rows,
                                              │                      warnings[] }
                                              │   SINGLE SOURCE OF TRUTH
                          ┌───────────────────┼─────────────────────┐
                          ▼                    ▼                     ▼
                 compare_bundles       annotate concept list   enrichment keys
                 groups by uid          (served, not FE-        (cognate / canonical /
                 (candidates per         recomputed)             flags / notes) by uid
                  member row)
                          │                    │
                   /api/compare/bundles   /api/concept-identity
                          └──────── ONE grouping, no bridge ────────┘
```

`ConceptIdentity` (already implemented):

```
@dataclass(frozen=True)
class ConceptIdentity:
    concepts: list[Concept]          # uid, label, members[], origin
    uid_by_row: dict[str, str]
    rows_by_uid: dict[str, list[str]]
    warnings: list[str]
```

`load_concept_identity(project_root)` computes the auto closure over
`concept_survey_links`, applies `concept-identity.json` overrides (authoritative
`manual:split` / `manual:merge`), assigns stable `uid`s (`c-<lowest-member-id>`,
collision-renamed), and reconciles new/orphaned rows with warnings — never
silently.

---

## 7. Phased migration

Each phase is independently shippable and independently valuable. Line ranges are
against `origin/main` at the time of writing and are indicative.

### Phase 1 — Surface the signal (MC-458-B, shipped)
- **Change:** in `compare_bundles.py` grouping (`~358–365`), when a `(survey,
  item)` link joins two rows whose glosses diverge (conservative heuristic),
  append a warning to the affected bundle's `warnings`. **Grouping unchanged.**
- **Why first:** zero behavior risk, immediately actionable in the existing
  warnings panel, and the sweep proves the heuristic is precise.
- **Out of scope:** any automatic re-grouping.

### Phase 2 — Wire the single source of truth
- **Change:** `build_compare_bundles` calls `load_concept_identity()` and groups
  rows by `uid` (`rows_by_uid`), deleting its private stem/pair union-find
  (`compare_bundles.py ~323–365`). Buckets/candidates build unchanged beneath.
- Serve identity over a new `/api/concept-identity`; **Annotate consumes it**
  instead of recomputing in `conceptGrouping.ts`. `findBundleForConcept()`
  (`src/lib/compareBundles.ts`) is then deletable — both sides key off `uid`.
- **Effect:** the stem merge and the gloss-blind pair merge are *gone*; identity
  is link-driven, override-correctable, and identical across Annotate and
  Compare by construction. Phase-1 warnings become Phase-2 override prompts.
- **Behavior delta to manage:** link-only grouping no longer auto-merges
  same-gloss rows that lack a link. Mitigate with a one-time backfill that
  proposes `manual:merge` overrides (or links) for current same-stem clusters,
  reviewed by the linguist — *not* an automatic merge.

### Phase 3 — Durability and correction UX
- Migrate `parse-enrichments.json` keys (cognate sets, canonical, flags, notes)
  from `csv_row_id` / bundle-label to **`uid`**, so a re-link or split never
  orphans a decision. Ship as an idempotent, dry-run-first migration.
- Ship the **split/merge UI** over `concept-identity.json`: a Phase-1/-2 warning
  becomes a one-click `manual:split` (or merge), durable and uid-keyed.

### Out-of-band data fixes (any time)
- Correct genuinely wrong links (e.g. the fog→rain off-by-one) directly via the
  survey-link editor — independent of the phases above.
- Add reciprocity / dangling-target detection to the survey-overlap write path
  (`python/survey_overlap.py`) so bad links are caught at write time, not just at
  grouping time.

---

## 8. Why this is the right long-term shape

- **Single source of truth.** One closure, one override file, one `uid`. The
  entire class of "Compare shows a variant Annotate doesn't" disappears by
  construction — not just the reported instances.
- **Identity ≠ gloss.** Removing the stem merge removes homonym over-merging and
  the transitive amplifier. Identity becomes explicit and auditable, never
  inferred from English text.
- **Fail loud, not silent.** Gloss-mismatch (Phase 1) and reciprocity / dangling
  detection (out-of-band) convert silent fusions into surfaced, actionable
  signals — the thing the overlap layer has none of today.
- **Non-destructive and reversible.** Corrections live in `concept-identity.json`
  as override deltas keyed by stable `uid`; `concepts.csv`, annotations, and raw
  links are never mutated. A wrong link *or* a wrong merge is fixable without
  data surgery.
- **Bounded blast radius, phased.** Phase 1 ships a pure signal with zero
  behavior change; Phase 2 swaps the grouping engine with a reviewed backfill;
  Phase 3 hardens durability. Each is reversible and independently testable.
- **Already specced and tested.** Engine A exists with a design doc and 11 tests
  and matches this intent precisely. The work is wiring and migration, not
  green-field design.

---

## 9. Acceptance criteria per phase

- **Phase 1:** suspect cross-gloss links appear in the affected bundle's warnings;
  clarifier variants do not; grouping output byte-identical. *(met by MC-458-B)*
- **Phase 2:** for every concept, Compare's bundle membership equals
  `concept_identity.rows_by_uid`; Annotate's concept list equals the same; the
  fog/rain and snow/ice cases group correctly *without* any link edit once an
  override exists; `findBundleForConcept()` removed.
- **Phase 3:** an enrichment decision survives a re-link and a split with no
  orphaning; the split/merge UI writes valid `concept-identity.json` overrides
  round-tripped by `identity_payload`.

---

## 10. References

- `python/concept_identity.py`, `python/test_concept_identity.py`,
  `docs/architecture/concept-identity.md` — Engine A.
- `python/compare_bundles.py` (union-find `~323–365`) — Engine B.
- `src/lib/conceptGrouping.ts`, `src/lib/compareBundles.ts`
  (`findBundleForConcept`) — Engine C and the bridge.
- `python/survey_overlap.py` (`concept_survey_links_for_row`) — the link layer.
