# Design — Concept Appendix Export with Cognate Matrix Decisions

**Status:** APPROVED (display refinements 2026-06-01) — building.
**Date:** 2026-06-01

## Goal

Let compare-mode users export a markdown concept appendix (per-speaker forms per survey concept),
**augmented with the cognate matrix decisions** that the legacy appendix lacks (cognate-set
letters, the accepted/split/merge verdict, borrowing flags, excluded speakers). The export is a
**standard, language/survey-neutral** document — nothing dataset-specific is hardcoded.

## Data sources (all already exist)

| Need | Source |
|---|---|
| Tag-filtered concepts + per-speaker IPA/ORTH forms + survey source items | `build_review_data()` in `python/export_review_data.py` |
| Cognate-set letters per concept (`{concept: {A: [spk…], B: […]}}`) | `parse-enrichments.json` → `manual_overrides.cognate_sets` (fallback `cognate_sets`) |
| Grouping verdict | `manual_overrides.cognate_decisions[concept] = {decision, ts}` |
| Borrowing flags | `manual_overrides.borrowing_flags[concept][speaker]` |
| Excluded speakers | `manual_overrides.speaker_flags[concept][speaker]` → rendered as `?` (BEAST2 missing = non-penalized) |

Letter→speaker resolution mirrors `build_nexus_text()` (`export_tools.py`): override sets win
over auto sets per concept; a speaker with a form but in no group = ungrouped (`·`).

## Neutrality (no dataset-specific text)

- Title and intro are generic — no language name, no survey name baked in.
- **Survey columns are derived dynamically** from the concepts' actual survey links; whatever
  surveys the project defines become the source-item line. No "KLQ/JBIL/Oxford" literals.
- **No `†` transliteration footnote, no per-survey prose note.** Those were SK/Oxford-specific.
- Speaker roster is listed plainly from `project.json` (no daggers, no group prose).

## The MCP tool

New tool `export_concept_appendix_md`, added to `EXPORT_TOOL_SPECS` / `EXPORT_TOOL_HANDLERS`
in `python/ai/tools/export_tools.py` (same pattern as `export_lingpy_tsv`).

```jsonc
{
  "name": "export_concept_appendix_md",
  "description": "Export a per-concept markdown appendix (per-speaker IPA/ORTH forms per survey concept), optionally annotated with cognate-set decisions. Without outputPath returns the full markdown; with outputPath writes inside the project.",
  "parameters": {
    "tag_id":        "string  (default custom-sk-concept-list)",
    "includeCognates":"boolean (default true) — when false, the plain forms-only appendix",
    "outputPath":    "string  (project-relative; omit for full-text return)",
    "dryRun":        "boolean"
  },
  "mutability": "mutating",        // writes only when outputPath given
  "supports_dry_run": true
}
```

- **No `outputPath`** → returns `{ markdown: "<full document>", concepts: N, speakers: M }`
  (the *whole* document, not a truncated preview — the appendix is small plain text and the
  frontend needs the full body to trigger a browser download).
- **`outputPath`** → writes the file inside the project and returns the path + counts.

## Frontend entry point

A new **"Export Concept Appendix (.md)"** button in the **Decisions** section of
`CompareTabContent.tsx`, beside the existing "Export LingPy TSV" button. It calls the MCP tool
(no `outputPath`), takes `result.markdown`, and triggers a client download named
`concept-appendix.md` via the existing `triggerDownload()` helper in `src/hooks/useExport.ts`.
`includeCognates` is `true` from the UI; the parameter exists so the MCP/agent path can also
produce the plain forms-only appendix.

---

## DISPLAY — exact rendered output

### Legend

- **Cog** column / matrix cell = the form's cognate-set letter (A, B, C …).
- `·` = form recorded but left **ungrouped** (no cognate decision for it yet).
- `?` = **missing or excluded** — speaker has no form for the concept, or was excluded from the
  set. `?` is BEAST2's non-penalized missing state, so excluded speakers don't bias compute.
- `⟳` after a letter = form flagged as a **borrowing**.
- Verdict words: **split** (multiple sets) · **accepted** (single set kept) · **merge** (sets merged to one) · **—** (no decision yet).

### Preamble (neutral)

```markdown
# Concept Appendix — per-speaker forms & cognate decisions

_Generated 2026-06-01 from the PARSE workspace (`custom-sk-concept-list` tag)._

Each concept is listed with its source item number in each elicitation survey, the IPA and
orthographic forms recorded for every studied speaker, and the cognate-set decisions made in
PARSE compare mode. Forms are matched to concepts by the annotation's time-aligned concept windows.

**Speakers (10).** Fail01, Fail02, Fail03, Kalh01, Kalh02, Mand01, Qasr01, Saha01, Badr01, Qorv01.

**Surveys.** KLQ · JBIL · Oxford.   <!-- derived from the project's actual survey links, not hardcoded -->

**Cognate column.** Cog letters (A, B, C …) are each form's cognate set. `·` = recorded but
ungrouped; `?` = no form, or speaker excluded from the set (non-penalized in compute);
`⟳` = borrowing. Per-concept verdict: split / accepted / merge / —. The next section is the
full speaker × concept cognate matrix.
```

### Top-level section — the cognate matrix (concepts as rows)

```markdown
## Cognate matrix

| # · Concept | Fail01 | Fail02 | Fail03 | Kalh01 | Kalh02 | Mand01 | Qasr01 | Saha01 | Badr01 | Qorv01 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 · ash  | B | ? | A | C | A | D | C | E | A | A | split |
| 2 · bark | A | ? | A | B | A | C | D | D | A | A | split |
| 3 · big  | A | A | A | B | B | C | B | C | A | B | split |
| …        |   |   |   |   |   |   |   |   |   |   |       |
```

(letter = cognate set · `·` = ungrouped · `?` = no form / excluded)

### Per-concept sections — forms table + cognate columns + verdict

Three additions vs. a plain forms appendix: a `**Cognate:**` verdict line, a `Cog` column, and a
`**Sets:**` summary line.

```markdown
### 3 · big
**KLQ:** 4.1  ·  **JBIL:** 169  ·  **Oxford:** 13
**Cognate:** split · 3 sets (A, B, C)

| Speaker | IPA                | ORTH            | Cog |
|---|---|---|---|
| Badr01  | gap                | gap             | A   |
| Fail01  | ɡap                | گەپ             | A   |
| Fail02  | ɡap                | دید             | ?   |   <!-- excluded speaker → ? -->
| Fail03  | gap                | gap             | A   |
| Kalh01  | buːtʃ; qaː; ɡoːɹaː | بۊچ; تاۊ; قەۊل… | B   |
| Kalh02  | gawra; gawrā       | gawra; gawrā    | B   |
| Mand01  | ɡoːda              | گەوورە          | C ⟳ |   <!-- borrowing -->
| Qasr01  | ɡoːra; ɡɔra        | گەورا; گەوورا   | B   |
| Saha01  | bikalan; …; ɡoːrɔ  | …; کەلەم; گەورە | C   |
| Qorv01  | gawra; gawrā       | gawra; gawrā    | B   |

**Sets:** A = {Badr01, Fail01, Fail03} · B = {Kalh01, Kalh02, Qasr01, Qorv01} · C = {Mand01 ⟳, Saha01} · excluded: Fail02
```

A concept with no cognate decisions yet renders `**Cognate:** —` and a `Cog` column of `·`, so
the export never blocks on undecided concepts.

## Build checklist

1. `/create-mc-task` → MC-NNN (required before any PARSE coding task).
2. `python/ai/tools/export_tools.py`: add spec, `build_concept_appendix_md(tools, include_cognates)` builder (reuses `build_review_data`, reads enrichments for cognate sets/decisions/borrowing/speaker flags), handler, registry entry. Surveys derived dynamically; no dataset literals.
3. `python/ai/tools/test_export_tools.py`: tests — forms-only output when `includeCognates=false`; cognate columns/verdict/sets/matrix present when true; excluded → `?`; ungrouped → `·`; borrowing → `⟳`; undecided-concept fallback; full-markdown return when no `outputPath`.
4. `src/components/CompareTabContent.tsx` + `src/hooks/useExport.ts`: button + download wiring; vitest coverage.
5. `tsc` + `vitest` + `python -m pytest` + build; open PR with `[MC-NNN-x]` title and labels; self-review.
