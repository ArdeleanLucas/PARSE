# Cross-survey concept linking

PARSE supports linking the same concept across multiple elicitation surveys (e.g. "father" from the JBIL list and "father" from the Kurdish Lexicon Questionnaire) so the workspace recognizes them as the same lexical concept. This guide covers the data model, the MCP tool that populates the link map, and the workflow for managing primary and alternate survey IDs in the UI.

## Overview

Many PARSE workspaces collect data using two or more standardized concept lists — the Jena-Bamberg Iranian List (JBIL), the Kurdish Lexicon Questionnaire (KLQ), custom surveys, and so on. The same English gloss often appears in multiple lists with different numbering: JBIL `nose=34`, KLQ `nose=1.5`. PARSE tracks each concept once in `concepts.csv` with a single primary `(source_survey, source_item)` pair, and stores alternates in a sidecar JSON. The UI surfaces those alternates as a flippable badge so you can switch between survey IDs without editing the CSV by hand.

## Data model

Two files in your workspace work together.

### `concepts.csv` — durable primary

The five-column CSV PARSE has always used:

```
id,concept_en,source_item,source_survey,custom_order
1,nose,1.5,KLQ,1
2,father,2.1,KLQ,2
```

One row per concept. The `(source_survey, source_item)` pair is the **primary** identifier. Exports (LingPy, NEXUS, CLEF) write out this primary value.

### `survey-overlap.json` — additive sidecar

JSON file in the workspace root. Stores alternates and per-speaker preferences:

```json
{
  "version": 1,
  "color_coding_enabled": true,
  "surveys": {
    "jbil": { "display_label": "JBIL", "display_color": "indigo" },
    "klq":  { "display_label": "KLQ",  "display_color": "rose" }
  },
  "concept_survey_links": {
    "1": { "jbil": "34" }
  },
  "speaker_choices": {
    "Fail01": { "1": "klq" }
  },
  "speaker_concept_survey_links": {
    "Qasr01": { "1": { "jbil": "32" } }
  }
}
```

| Field | Purpose |
|---|---|
| `surveys` | Registry of survey IDs → display label + color |
| `concept_survey_links` | For each concept, the alternate `{survey_id: source_item}` pairs that supplement the CSV primary |
| `speaker_choices` | Per-speaker preference: when speaker S annotates concept C, prefer survey X |
| `speaker_concept_survey_links` | Per-speaker per-concept survey/source_item actually used during their elicitation |
| `color_coding_enabled` | Toggle for color-coded badges in the sidebar |

A concept with primary `(KLQ, 1.5)` and `concept_survey_links["1"] = {"jbil": "34"}` is linked to both surveys. The CSV row reflects whichever is currently primary; the sidecar holds the rest.

## How linking works

1. **Detect.** A script (`scripts/populate_cross_survey_links.py`) or its MCP wrapper reads a reference lexeme CSV and finds workspace concepts whose English gloss appears in the reference.
2. **Validate.** By default, only single-word concepts (no parentheses, commas, or whitespace in `concept_en`) are matched — this avoids false equivalences between elicitation variants like `father (vocative)` and bare `father`. The reference's primary entry for that survey must also match the workspace's legacy primary, or the row is flagged as a conflict and skipped.
3. **Write.** Matched concepts get sidecar entries in `concept_survey_links` for the surveys they're linked to. `concepts.csv` stays untouched.
4. **Surface.** The React UI reads `concept_survey_links` at render time. A concept with two or more linked surveys shows an interactive badge.

### Interaction modes

The shared `<SurveyBadge>` component (in the concept sidebar and the right-panel "Active survey" line) adapts to context:

| Context | Click behavior |
|---|---|
| 1 linked survey | Static badge — no interaction |
| 2 linked surveys, active speaker | Cycle: writes a per-speaker preference into `speaker_choices` (non-destructive) |
| 2 linked surveys, no active speaker | **Promote**: rewrites `concepts.csv` primary to the next survey and demotes the old primary into `concept_survey_links` |
| 3+ linked surveys | Opens a popover menu of all options; selecting one performs the cycle or promote action depending on speaker state |

The promote action calls `POST /api/concepts/{id}/promote-survey-primary` — a global, no-speaker endpoint that changes the canonical primary for the concept. It writes an atomic CSV backup (`concepts.csv.bak-<timestamp>-pre-promote-<concept_id>`) before each rewrite.

## Using the MCP tool

The `populate_cross_survey_links` MCP tool runs the same logic as the CLI script but is callable by the AI agent. The workspace root comes from the agent's `project_root`; you only supply the reference CSV path.

### Reference CSV format

Required columns (case-insensitive header):

```
source,id,lexeme
JBIL,1,one
JBIL,2,two
KLQ,1.1,hair (collective)
KLQ,1.5,nose
KLQ,2.1,father
```

- `source` — survey ID, case-insensitive (normalized to lowercase internally). Common values: `JBIL`, `KLQ`, or any custom survey ID you've registered in `survey-overlap.json::surveys`.
- `id` — `source_item` exactly as it should appear in the CSV (e.g. `1.1`, `34`).
- `lexeme` — English gloss. Match is case-insensitive after collapsing whitespace.

The CSV can contain rows for any number of surveys. Duplicate entries for the same `(survey, lexeme)` pair with different IDs are flagged as `reference_ambiguous` and the affected concept is skipped.

### Tool parameters

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `referencePath` | string | yes | — | Absolute path or workspace-relative path to the reference CSV |
| `dryRun` | boolean | yes | — | `true` returns the would-add summary without writing; `false` applies |
| `singleWordOnly` | boolean | no | `true` | When true, only matches concepts whose `concept_en` has no parens, commas, or whitespace |

### Example dry-run call

```jsonc
{
  "name": "populate_cross_survey_links",
  "arguments": {
    "referencePath": "imports/lexemes_combined.csv",
    "dryRun": true,
    "singleWordOnly": true
  }
}
```

Response shape:

```jsonc
{
  "dryRun": true,
  "matched": [
    {
      "concept_id": "1",
      "concept_en": "nose",
      "legacy_primary": { "survey": "klq", "source_item": "1.5" },
      "reference_links": { "jbil": "34", "klq": "1.5" }
    }
    // ...
  ],
  "would_add": [
    { "concept_id": "1", "concept_en": "nose", "links": { "jbil": "34" } }
    // ...
  ],
  "conflicts": [
    {
      "concept_id": "12",
      "concept_en": "rain",
      "reason": "legacy_primary_mismatch",
      "legacy_primary": { "survey": "jbil", "source_item": "126" },
      "reference_primary": { "survey": "jbil", "source_item": "999" }
    }
  ],
  "skipped_multiword": [
    { "concept_id": "2", "concept_en": "father (vocative)", "reason": "single_word_only" }
  ]
}
```

Inspect `would_add` and `conflicts` before applying. To apply, call again with `dryRun: false`:

```jsonc
{
  "name": "populate_cross_survey_links",
  "arguments": {
    "referencePath": "imports/lexemes_combined.csv",
    "dryRun": false
  }
}
```

The response now includes a `sidecar_diff` showing the pre-apply and post-apply state of `concept_survey_links`. The operation is idempotent — calling apply a second time on the same inputs produces no further write.

### Equivalent CLI invocation

Same logic outside the agent:

```bash
PYTHONPATH=python python3 scripts/populate_cross_survey_links.py \
  --reference imports/lexemes_combined.csv \
  --workspace ~/parse-workspace \
  --apply   # omit for dry-run
```

## End-to-end workflow

1. **Prepare** a reference lexeme CSV with `source,id,lexeme` columns covering every survey you want PARSE to know about. For the JBIL+KLQ case, this is one file with both surveys' entries combined.
2. **Place** the file in the workspace (e.g. `~/parse-workspace/imports/lexemes_combined.csv`). Any path readable by the workspace works.
3. **Dry-run.** Call `populate_cross_survey_links` with `dryRun: true`. Read the `would_add` list to confirm the proposed links and the `conflicts` list for anything to investigate.
4. **Apply.** Re-call with `dryRun: false`. `survey-overlap.json::concept_survey_links` now contains alternates for the matched concepts.
5. **Verify in the UI.** Open PARSE. Concepts with multiple linked surveys now show a clickable badge in the sidebar. The right-panel "Active survey" line is also flippable.
6. **Flip primaries** (no-speaker context). Click a badge while browsing the concept list to promote a sidecar entry to primary. PARSE rewrites `concepts.csv` (with a `.bak-*` backup) and moves the old primary into the sidecar so nothing is lost.
7. **Per-speaker preferences** (annotation context). With a speaker active, clicking the badge sets a per-speaker preference under `speaker_choices`. The CSV primary is unchanged; only what this speaker sees changes.

## Troubleshooting

**Badge isn't clickable.** Only one survey is linked. Check `survey-overlap.json::concept_survey_links` for that concept ID — if it's missing or empty, the population step didn't match it. Re-run the dry-run and check `conflicts` and `skipped_multiword`.

**Concept appears in `conflicts` with `legacy_primary_mismatch`.** The workspace's CSV primary disagrees with the reference for that survey. Fix by either correcting `concepts.csv` or correcting the reference. Don't override — a mismatch usually reflects a real disagreement worth resolving.

**Concept appears in `conflicts` with `reference_ambiguous`.** The reference CSV has multiple rows for the same `(survey, lexeme)` pair with different IDs. Deduplicate the reference.

**Concept appears in `conflicts` with `existing_sidecar_mismatch`.** The sidecar already has a different `source_item` recorded for that concept+survey pair. Either edit `survey-overlap.json` to remove the stale entry, or update the reference.

**Multi-word concepts not matched.** Expected — the single-word filter is on by default to avoid false matches between elicitation variants. Pass `singleWordOnly: false` to relax (use with care; review the resulting `would_add` carefully).

**Where do exports look?** LingPy, NEXUS, and CLEF export from the CSV primary, not the sidecar. To export a different survey's IDs, promote that survey to primary first (single click in the UI or call the endpoint).

## See also

- `POST /api/concepts/{id}/promote-survey-primary` — promote a sidecar link to primary (also called automatically by the badge click in no-speaker mode)
- `POST /api/concepts/{id}/survey-links` — add or remove a sidecar entry directly
- `python/survey_overlap.py` — sidecar read/write helpers (Python)
- `src/components/shared/SurveyBadge.tsx` — UI component that renders the flippable badge
