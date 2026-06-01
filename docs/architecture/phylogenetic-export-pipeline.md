# Phylogenetic export pipeline: structure and data flow

How PARSE turns a workspace (annotations + cognate decisions) into the LingPy TSV
and NEXUS matrix that feed phylogenetic inference (BEAST2 / LingPy / LexStat),
**through the MCP export tools** — no custom scripts required.

This document complements [`cognate-sets-and-matrix.md`](./cognate-sets-and-matrix.md),
which explains how cognate *decisions* become COGIDs. Here we document the
end-to-end *export structure*: the inputs, the consolidation step, the output file
shapes, the MCP surface, and the readiness diagnostics.

---

## 1. End-to-end data flow

```
 INPUTS (a PARSE workspace)
 ─────────────────────────────────────────────────────────────────────────────
 annotations/*.parse.json     parse-enrichments.json        parse-tags.json      concepts.csv
 per speaker:                 manual_overrides.cognate_      concept-tag          id -> gloss,
   concept tier (text +         sets: {concept_id:           membership           source_survey,
   stable concept_id)            {group: [speakers]}}        (e.g. the thesis     source_item
   ipa tier (surface form)                                    concept list)
        │                              │                          │                    │
        ▼                              ▼                          │                    ▼
  load_annotations()         _resolve_effective_                  │          build_canonical_gloss_index()
  forms keyed by             cognate_sets()                       │          which concept_ids are the
  STABLE concept_id          computed ∪ manual (manual wins)      │          SAME gloss (survey overlap)
        │                              │                          │                    │
        │                              └───────────┬──────────────┴────────────────────┘
        │                                          ▼
        │                         [OPTIONAL] CONSOLIDATION  (conceptTag / consolidate)
        │                         • restrict to a tag's concepts
        │                         • fold survey-overlap duplicate ids into ONE canonical
        │                           character  (big = 53 + 150  ->  one "big")
        │                                          │
        └──────────────────────┬───────────────────┘
                                ▼
                       _build_cogid_lookup()
                       assign an integer COGID to each (concept, cognate group)
                                │
              ┌─────────────────┴──────────────────┐
              ▼                                     ▼
     export_wordlist_tsv()                  build NEXUS matrix
     LingPy TSV — one row per               NEXUS — one column per
     (concept, speaker) token               (concept, cognate group)
              │                                     │
              └─────────────────┬──────────────────┘
                                ▼
                  BEAUti  ->  BEAST2 XML  ->  MCMC  ->  posterior tree
                  (BEAST2 tooling is external; PARSE's deliverable is the NEXUS/TSV)
```

All cognate/COGID code lives in `python/compare/cognate_compute.py`. Consolidation
lives in `python/compare/consolidated_matrix.py`. The MCP tool handlers live in
`python/ai/tools/export_tools.py` and `python/ai/workflow_tools.py`.

---

## 2. Inputs — where the data lives

| Artifact | Path | Role in the export |
|---|---|---|
| Annotations | `annotations/<speaker>.parse.json` | Per-speaker surface forms. The concept tier carries the human label (`text`) **and** the stable `concept_id`; the ipa tier carries the form. |
| Cognate decisions | `parse-enrichments.json` → `manual_overrides.cognate_sets` | `{concept_id: {group_letter: [speakers]}}` — the committed canonical cognate decision, keyed by concept id. **This is what the matrix reads.** |
| Borrowing flags | `parse-enrichments.json` → `manual_overrides.borrowing_flags` | Per-(concept, speaker) loan flag → the TSV `BORROWING` column. |
| Concept tags | `parse-tags.json` | Tag → member concept ids. Lets an export restrict to a thesis concept list. |
| Concept table | `concepts.csv` | `id, concept_en, source_survey, source_item`. Drives gloss normalization (which ids are the same concept across surveys). |

---

## 3. The consolidation step (survey overlap)

A gloss is often elicited under **more than one survey id** — e.g. *big* is
concept `53` (survey KLQ) **and** concept `150` (survey JBIL). Without
consolidation, each id becomes its own character block, double-counting the gloss:

```
 RAW (default — keyed by concept_id)            CONSOLIDATED (conceptTag / consolidate)
 ──────────────────────────────────            ────────────────────────────────────────
  concept 53  "big" (KLQ)  -> 53_A  53_B          canonical "big" {53,150} -> big_A  big_B
  concept 150 "big" (JBIL) -> 150_A 150_B         (one character block)
            = 4 columns for one gloss                       = 2 columns
```

Consolidation is **safe and deterministic** because it only collapses
**byte-identical** duplicate columns (`safe_union`): the two ids must carry the
exact same cognate partition. When the per-id group letters differ
(`needs_recluster`) the columns are **kept separate with a warning** — their
letters are not cross-comparable, so merging would require a re-clustering pass,
which the export does not invent. This reuses the MC-439 audit
(`python/concept_character_audit.py`), so the export and the audit always agree.

> Scope note: consolidation currently folds **survey-overlap** duplicates. It does
> not strip parenthetical **clarifiers** (`dry` vs `dry (land)`); the legacy review
> export (`export_review_data.py`) does that via `strip_clarifier`. Aligning the
> two normalizations is tracked separately.

---

## 4. Output structure A — LingPy wordlist TSV

One row per (concept, speaker) token. Columns:

```
ID   CONCEPT   DOCULECT   IPA      COGID   TOKENS       BORROWING
1    big       Mand01     gewra    1       g e w r a    0
2    big       Qasr01     gewra    1       g e w r a    0
3    big       Saha01     kalan    2       k a l a n    0
4    small     Mand01     biçûk    7       b i ç û k    0
     │         │          │        │       │            │
     │     canonical   surface   cognate  space-split   1 = borrowed
     │      gloss       IPA       class    segments      0 = not
   row id  (DOCULECT = LingPy's term for a "language"/speaker)
```

- **CONCEPT** is the canonical gloss, so LingPy groups every form of a gloss
  together (even across folded survey ids).
- **COGID** is an integer cognate-class label. `0` means *uncoded* — the concept
  has no committed cognate decision for that speaker. COGID integers are arbitrary
  positional labels; only the *partition* (which forms share a COGID within a
  concept) is meaningful.

---

## 5. Output structure B — NEXUS character matrix

One taxon per speaker; one binary character per (concept, cognate group).

```
#NEXUS

BEGIN TAXA;
    DIMENSIONS NTAX=14;                 <- one taxon per speaker
    TAXLABELS  Mand01 Qasr01 Saha01 Khan01 ... ;
END;

BEGIN CHARACTERS;
    DIMENSIONS NCHAR=149;               <- one column per (concept, cognate group)
    FORMAT DATATYPE=STANDARD MISSING=? GAP=- SYMBOLS="01";
    CHARSTATELABELS  1 big_A, 2 big_B, 3 small_A, 4 small_B, ... ;
    MATRIX
        Mand01    1 0 0 1 ...           <- 1 = this speaker's form is in this cognate group
        Qasr01    1 0 0 1 ...           <- 0 = has a form for the concept, but a different group
        Saha01    0 1 0 1 ...
        Khan01    ? ? ? ? ...           <- ? = no form for this concept (missing)
    ;
END;
```

**Character encoding** (per speaker, per (concept, group) column):

| Symbol | Meaning |
|---|---|
| `1` | The speaker's form for this concept is in **this** cognate group. |
| `0` | The speaker **has** a form for this concept, but in a **different** group. |
| `?` | The speaker has **no** form for this concept. This is **missing data — a valid, expected NEXUS state**, not an error. Comparative wordlists are routinely sparse; BEAST2 handles `?` natively. |

A *fully* `?` taxon (no forms for any exported concept) contributes nothing and is
the one missingness case the readiness check flags (§7).

---

## 6. The MCP surface — how a user runs an export

All exports are driven by MCP tools (HTTP bridge `POST /api/mcp/tools/<name>`,
the stdio MCP server, or the agent chat path). **No scripts are required.**

| Tool | Writes | Key parameters |
|---|---|---|
| `export_lingpy_tsv` | `wordlist.tsv` | `outputPath`, `conceptTag`, `consolidate`, `dryRun` |
| `export_nexus` | `dataset.nex` | `outputPath`, `conceptTag`, `consolidate`, `dryRun` |
| `export_beast2_xml` | `analysis.xml` | `outputPath`, `conceptTag`, `consolidate`, `chainLength`, `dryRun` |
| `export_complete_lingpy_dataset` | both (a bundle) | `outputDir`, `conceptTag`, `consolidate`, `with_contact_lexemes`, `dryRun` |

`export_beast2_xml` wraps the same character matrix as `export_nexus` into a
self-contained BEAST 2.7 analysis (binary substitution model, Yule tree prior,
strict clock), so the chain reaches a runnable analysis without a BEAUti step:

```
beast analysis.xml      ->  analysis.log + analysis.trees
treeannotator -burnin 10 analysis.trees analysis.mcc.tree
```

Parameter semantics:

- **`conceptTag`** — restrict the matrix to a tag's concepts (e.g. the thesis
  concept list) **and** consolidate survey-overlap duplicates.
- **`consolidate`** — consolidate without restricting (implied by `conceptTag`).
- **`outputDir` / `outputPath`** — destination (date-stamp it to avoid clobbering
  prior evidence).
- **`dryRun`** — preview counts + readiness without writing.

Example — a consolidated, thesis-tag-only bundle in one MCP call:

```json
{
  "conceptTag": "custom-sk-concept-list",
  "consolidate": true,
  "outputDir": "exports/beast2/2026-05-31-thesis",
  "dryRun": false
}
```

Response carries the artifact paths plus a `consolidation` summary
(`collapsed_groups`, `needs_recluster_groups`, `character_count`, `concept_count`)
and the readiness fields below.

---

## 7. Readiness diagnostics

Every export response distinguishes **"file written"** from **"phylogenetically
usable"** via `beast2_ready` (bool) and `warnings` (list). Warnings fire only on
genuine no-go states:

| Warning | Meaning |
|---|---|
| all `COGID = 0` | No cognate decisions committed → the wordlist is not informative. |
| `NCHAR = 0` | No cognate sets → the matrix has no characters. |
| fully-missing taxa | One or more speakers have **no** forms for any exported concept (all `?`). |

`?` cells on their own are **not** flagged — missing data is normal and valid.

---

## 8. Worked example — concept "hair"

`hair` is elicited under several survey ids; the committed canonical decision (the
one shown in Compare) folds them into one set with three cognate groups across the
speakers, e.g. `{A: [Fail03, Khan02, Mand01, Qasr01, Qorv01, Saha01], B: [Fail01],
C: [Badr01, Kalh01, Kalh02]}`.

- **Consolidated** export emits one block for `hair`: columns `hair_A hair_B hair_C`.
- **Raw** export (no consolidation) would emit that block once per survey id.
- A speaker with no `hair` form gets `?` in all three columns; a speaker in group
  `A` gets `1 0 0`.

---

## 9. Code references

- `python/compare/cognate_compute.py` — `load_annotations`,
  `_resolve_effective_cognate_sets`, `_build_cogid_lookup`, `export_wordlist_tsv`.
- `python/compare/consolidated_matrix.py` — `build_consolidated_cognate_sets`,
  `build_nexus_from_sets`, `build_wordlist_rows`, `tag_concept_ids`.
- `python/concept_character_audit.py` — the byte-identical / `needs_recluster`
  classification reused by consolidation.
- `python/ai/tools/export_tools.py` — `export_lingpy_tsv`, `export_nexus`,
  readiness helpers.
- `python/ai/workflow_tools.py` — `export_complete_lingpy_dataset`.
- Companion: [`cognate-sets-and-matrix.md`](./cognate-sets-and-matrix.md).
```
