# Comparative-concept identity

> How PARSE decides **what counts as one concept** for Compare and for the
> phylogenetic character matrix — and how it keeps every elicited form visible
> for the linguist to judge.

This document is for the **linguist/user**: it explains where your data comes
from, how it is grouped, and what you control. The implementation lives in
[`python/concept_identity.py`](../../python/concept_identity.py).

---

## 1. The problem in one sentence

The same meaning is usually recorded in **several places** — across surveys
(KLQ vs JBIL) and as multiple takes on one prompt — but the phylogenetic matrix
needs **one row per concept**, with **one cognate state per speaker**. So PARSE
must *consolidate* all those forms under one identity **without** throwing any
of them away, and **without** deciding for you which are "the same".

---

## 2. The four data layers

PARSE keeps a deliberately tiny, durable inventory and layers everything else as
optional JSON **sidecars** beside it. Nothing here rewrites your transcriptions.

```
 workspace/
 ├── concepts.csv ................ THE INVENTORY (durable, 5 columns)
 │       id, concept_en, source_item, source_survey, custom_order
 │       → one row per SURVEY ITEM (an elicitation prompt)
 │
 ├── survey-overlap.json ......... LINKS (curated by you, in Annotate)
 │       concept_survey_links: "this row == that survey item in another survey"
 │
 ├── concept-identity.json ....... CONCEPT IDENTITY  ← new sidecar (this doc)
 │       the materialised "what is one concept", incl. your split/merge edits
 │
 ├── parse-enrichments.json ...... DECISIONS
 │       cognate sets, canonical picks, flags, notes  (keyed by concept uid)
 │
 └── annotations/<speaker>.parse.json . THE FORMS
         concept / ipa / ortho tiers; each interval = one recorded realization
```

Two multiplicities live in this data, and they are different things:

| Multiplicity | Where it lives | Example |
|---|---|---|
| **Same concept across surveys** | two `concepts.csv` rows, joined in `survey-overlap.json` | `green` = KLQ 5.4 (row 91) ↔ JBIL 177 (row 385) |
| **Several forms on one item** | multiple intervals on one `concept_id` in an annotation | `to fly` (row 122): two recorded realizations (A, B) |

Both must end up **under one concept** in Compare. Neither must be silently
dropped.

---

## 3. How identity is built: closure → override

A *comparative concept* is computed in two stages. The first is automatic; the
second is **yours**.

```
   concepts.csv rows ─┐
                      ├─►  (1) CLOSURE  ─►  auto concepts  ─►  (2) OVERRIDES  ─►  final concepts
 survey-overlap links ┘        (suggest)                          (you decide)        (used by Compare)
```

### Stage 1 — Closure (the automatic suggestion)

Think of it as a graph:

- **Node** = one `concepts.csv` row (a survey item).
- **Edge** = one *explicit cross-survey link* you drew in `survey-overlap.json`.
- A **concept** = a connected group of rows (a "component").

Closure means links chain: if `A` is linked to `B`, and `B` to `C`, then
`A`, `B`, `C` are all one concept — even if you only linked `A↔B` and `B↔C`.
This is what "same as" *means*; it also saves you work (link each new survey to
**one** existing member, not all of them).

```
   green:                              transitive chain (3 surveys):

   row 91  ──{jbil:177}──►  row 385       KLQ ──► JBIL ──► EXT
   (KLQ 5.4)            (JBIL 177)          \_____________/
        ◄──{klq:5.4}────                  one concept, though KLQ↔EXT
                                          was never drawn directly
   = ONE concept "green"
```

**Important rule — a shared survey item is _not_ a link.** One prompt can elicit
several distinct concepts (e.g. JBIL item 319 covers a whole pronoun paradigm:
*I / I am teaching / I saw you …*). Those rows share `source_item` but are **not**
joined — only an explicit link joins rows.

### Stage 2 — Overrides (your authority)

Closure is only a **suggestion**. It cannot make linguistic judgments, and your
real data contains cases it gets wrong:

```
   snow / ice — JBIL records both under ONE item (123); KLQ separates them:

   row 44  snow (KLQ 3.4) ─┐
   row 144 snow (JBIL 123) ─┼─► closure merges all four into ONE concept
   row 45  ice  (JBIL 123) ─┤     (because JBIL item 123 is BOTH snow and ice)
   row 617 ice  (KLQ 3.5) ─┘
```

Only you can decide whether `snow` and `ice` are one character or two. You record
that in `concept-identity.json`, and it **overrides** the closure:

```jsonc
// concept-identity.json
{
  "version": 1,
  "concepts": [
    { "uid": "c-snow", "label": "snow", "members": ["44", "144"], "origin": "manual:split" },
    { "uid": "c-ice",  "label": "ice",  "members": ["45", "617"], "origin": "manual:split" }
  ]
}
```

The rule: **a concept listed in the sidecar is authoritative for the rows it
claims.** Everything you don't touch keeps the automatic grouping. The algorithm
proposes; you dispose.

---

## 4. What you get back

For a workspace, PARSE produces a list of concepts plus two lookups:

```
 Concept
 ├── uid      "c-91"            ← stable id; DECISIONS key off this
 ├── label    "green"          ← cleanest gloss among members (editable)
 ├── members  ["91", "385"]    ← the concepts.csv rows it consolidates
 └── origin   "auto" | "manual:split" | "manual:merge"

 uid_by_row:  { "91": "c-91", "385": "c-91", ... }   row  → concept
 rows_by_uid: { "c-91": ["91", "385"], ... }          concept → rows
 warnings:    ["…"]                                   non-fatal problems (see below)
```

`uid` is the anchor for the **whole comparative workflow**: a concept's cognate
state, canonical pick, flags and notes all key off `uid`, which is exactly what
makes **"one cognate state per concept"** well-defined.

**Nothing fails silently.** Because the override file holds *your* authoritative
decisions, any problem applying it is surfaced in `warnings` rather than quietly
reverting to the auto grouping: an unreadable/malformed override file, member
ids that no longer exist in the inventory (dropped), or a uid that collides with
another concept (renamed). The grouping stays usable; the warning tells you what
to fix.

### Live numbers (current workspace, pure closure, no overrides yet)

```
 549 concepts =  504 singletons        (single-survey concepts, e.g. "to fly")
              +   42 pairs             (cross-survey, e.g. "green" = KLQ ↔ JBIL)
              +    1 triple
              +    2 quads             (incl. the snow/ice over-merge to split)
```

---

## 5. How Compare uses it (the lens)

Compare becomes a **pure projection** over one concept:

```
                ┌──────────────────────── concept "green" (uid c-91) ───────────────────────┐
   Annotate     │  members: row 91 (KLQ 5.4)   +   row 385 (JBIL 177)                        │
   (forms in)   │                                                                            │
                │   per taxon, gather EVERY form across BOTH rows (all A/B intervals):        │
                │                                                                            │
                │     Fail01   KLQ /aːsuːdʒəɜl/   JBIL /saʊz/   ← you pick canonical          │
                │     Qasr01   KLQ /soːza/        JBIL /soʊz/                                 │
                │     Khan01                      JBIL /a/  (1 form → auto-canonical)         │
                │                                                                            │
                │   → one canonical per taxon  →  one cognate state (exports 1 / 0 / ?)       │
                └────────────────────────────────────────────────────────────────────────────┘
```

Guarantees this identity gives Compare:

- **Total** — every form is reachable; nothing collapses to "the first one".
- **Consolidated** — both surveys' forms appear together, under one concept.
- **Non-deciding** — all forms shown with provenance; *you* choose canonical and
  judge synonymy. PARSE never hides or auto-merges forms.
- **Stable** — decisions key off `uid`, so they survive re-import and re-grouping.

---

## 6. What this module does and does not do

**Does:** compute concept identity (closure + your overrides), expose
`load_concept_identity(project_root)`, and serialise the result.

**Does not (yet — follow-up work):**

- wire identity into `compare_bundles.py` (group bundles by `uid`, enumerate
  every interval instead of only the first);
- migrate `parse-enrichments.json` decision keys from per-row to per-`uid`;
- the Compare split/merge UI for editing `concept-identity.json`.

No data migration is required for this layer: `concepts.csv`, the annotations,
and `survey-overlap.json` are unchanged; this sidecar is purely additive.

---

## 7. Glossary

| Term | Meaning |
|---|---|
| **Survey** | an elicitation instrument (KLQ, JBIL, EXT) |
| **Survey item** | a numbered prompt in a survey (`KLQ 5.4`); one `concepts.csv` row |
| **Form / realization** | one recorded interval (IPA/ortho/time) for a speaker |
| **A/B** | multiple intervals (forms) recorded on one item by one speaker |
| **Link** | a curated "this row == that survey item" assertion (`survey-overlap.json`) |
| **Concept / character** | one comparative meaning = one matrix row = one `uid` |
| **Closure** | chaining links into connected concepts (the auto suggestion) |
| **Override** | your authoritative split/merge in `concept-identity.json` |
