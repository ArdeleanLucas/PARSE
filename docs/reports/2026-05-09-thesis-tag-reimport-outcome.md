# Thesis tag re-import validation outcome — 2026-05-09

## Scope

After PR #313 (`feat(tags): import base labels across concept variants`) merged to `main`, the first validation pass was invalid because it audited legacy `annotations/<speaker>.json` files. The active PARSE annotation API/UI uses `annotations/<speaker>.parse.json` when present.

A second UI-path defect was then found from Lucas's Saha01 check: active `.parse.json` data had the Thesis tag on the relevant concept IDs, but the React sidebar's custom-tag filter only checked the grouped row's parent `key`. Grouped/source-item concepts keep their true concept IDs under `variants` / underlying keys, so tagged words such as `cold`, `ear`, `head`, and `sun` could be hidden even though their active annotation `concept_tags` were correct.

This corrected pass validates both the active `.parse.json` annotation files and the grouped-sidebar tag-filter semantics.

- CSV: `/mnt/c/Users/Lucas/Thesis/concepts.csv`
- Rows: 82 (`id`, `concept_en`)
- Tag: `custom-sk-concept-list`
- Workspace: `/home/lucas/parse-workspace`
- Original pre-apply snapshot: `/tmp/parse-workspace-annotations-pre-thesis-reimport-20260508T133925Z`
- Corrective pre-apply snapshot: `/tmp/parse-workspace-annotations-pre-thesis-reimport-active-fix-20260508T140022Z`

## Root causes fixed

1. **Backend propagation targeted the wrong annotation family.** PR #313 skipped `*.parse.json` and therefore wrote only legacy `*.json` files. Corrective code now includes `*.parse.json` as tag-import targets and prefers `Speaker.parse.json` over `Speaker.json` when both exist.
2. **Backend re-import accumulated stale tag state.** Corrective code replaces the global tag concept list instead of unioning stale concepts, and reconciles stale per-speaker memberships by removing this tag from concept IDs outside the imported set.
3. **Frontend tag filtering ignored grouped concept IDs.** `ParseUI` now checks all underlying concept keys for grouped/variant rows when applying custom tag filters, so a Thesis-tagged variant remains visible in the speaker-scoped sidebar.

## Tool-surface and dry-run result

MCP `list_tools` exposed `import_tag_csv` with both new parameters:

- `matchAllVariants` default `true`
- `propagateToSpeakers` default `true`

Corrective dry-run through the MCP adapter returned:

- `matchedCount`: 82
- `unmatchedCount`: 0
- `matchedConceptCount`: 120

The May-03 missing base labels now all resolve to at least one PARSE concept id: `ash`, `bark`, `cold`, `ear`, `egg`, `fly`, `head`, `horn`, `hot`, `night`, `sun`, `this`, `tongue`, `tooth`, `you`.

## Corrective apply payload

Apply through the MCP adapter after the `.parse.json` fix returned:

```json
{
  "ok": true,
  "dryRun": false,
  "tagId": "custom-sk-concept-list",
  "tagName": "custom-sk-concept-list",
  "assignedCount": 120,
  "propagatedSpeakerCount": 9,
  "propagatedConceptAssignments": 259,
  "removedConceptAssignments": 1
}
```

`Saha01.parse.json` now has 100 tagged concept IDs folded to all 82 thesis labels, with no missing or extra folded labels.

## Saha01 UI-path check

The concept-list/UI simulation after the frontend filter fix gives:

- Saha01 Thesis + speaker-scoped sidebar count: 83 grouped rows.
- The count is 83 rather than 82 because `you (sg.)` and `you` are separate PARSE source items while the thesis CSV has one folded base label `you`.
- `they` is not in the Thesis-tagged sidebar result.
- Lucas's listed words are all present in the corrected Thesis-tagged Saha01 sidebar result: `black`, `cold`, `ear`, `hair`, `head`, `I`, `new`, `red`, `skin`, `sun`, `we`, `white`, `yellow`.

## Active `.parse.json` after counts

| Speaker | After tagged ids | After folded base labels | Missing folded thesis labels | Extra folded labels |
|---|---:|---:|---|---|
| Fail01 | 102 | 80 | ash; bark |  |
| Fail02 | 90 | 80 | ash; bark |  |
| Kalh01 | 103 | 82 |  |  |
| Khan01 | 110 | 82 |  |  |
| Khan02 | 91 | 77 | i; knee; skin; we; you |  |
| Khan03 | 76 | 75 | i; sister; skin; that; this; we; you |  |
| Khan04 | 88 | 80 | ash; bark |  |
| Mand01 | 101 | 82 |  |  |
| Qasr01 | 102 | 82 |  |  |
| Saha01 | 100 | 82 |  |  |

Khan02 and Khan03 now have thesis-tag membership in active `.parse.json` files; they still cannot reach 82 folded labels because their annotation payloads do not contain the missing concept IDs listed above.

## Still-uncovered labels and reason

There are no dry-run-unmatched thesis labels. The remaining post-apply per-speaker gaps are due to absent matching concept IDs in the affected active speaker annotation payloads, not label-resolution failure:

- `Fail01`: no annotation concept ID for `ash` (`538`) or `bark` (`534`).
- `Fail02`: no annotation concept ID for `ash` (`538`) or `bark` (`534`).
- `Khan02`: no annotation concept ID for `I` (`517`), `knee` (`275`), `skin` (`277`), `we` (`519`), or `you` (`518`, `520`).
- `Khan03`: no annotation concept ID for `I` (`517`), `sister` (`16`, `138`), `skin` (`277`), `that` (`506`), `this` (`504`, `505`, `547`), `we` (`519`), or `you` (`518`, `520`).
- `Khan04`: no annotation concept ID for `ash` (`538`) or `bark` (`534`).

## Go / no-go

**Partial go after correction:** active `Saha01.parse.json` now covers all 82 folded thesis labels, and the corrected React sidebar filter keeps the listed tagged Saha01 concepts visible while excluding `they`. The strict every-active-speaker criterion remains **no-go** because five active speaker annotation files lack the listed concept IDs and therefore cannot be fully tagged by propagation alone.
