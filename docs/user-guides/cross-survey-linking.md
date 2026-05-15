# Cross-survey concept linking

Use this guide when two or more word lists, questionnaires, or elicitation surveys contain the same concept but use different item IDs. PARSE is not tied to any one language, survey, or research project. You provide a small reference CSV that says:

> Survey **A** calls this concept item **001**; survey **B** calls the same concept item **A-10**.

The MCP tool reads that CSV, previews the safe links it can add, and then writes those links into the workspace only after you run it with `dryRun: false`.

## Quick answer: the CSV format

Create a CSV with these three columns:

```csv
source,id,lexeme
```

| Column | What to put there | Example value |
|---|---|---|
| `source` | The survey/list name or code. Use any stable name that makes sense for your project. | `SurveyA`, `SurveyB`, `WordList2024` |
| `id` | The item number or item code from that survey. PARSE treats it as text, so keep punctuation and leading zeros if your survey uses them. | `001`, `A-10`, `4.2` |
| `lexeme` | The concept gloss that matches `concept_en` in PARSE's `concepts.csv`. This is the meaning label, not a speaker's actual word form. | `water`, `fire`, `eat` |

Header names are case-insensitive, so `Source,ID,Lexeme` also works. Extra columns may be present, but the tool only uses `source`, `id`, and `lexeme`. Save the file as a UTF-8, comma-delimited `.csv` file.

### Blank template

```csv
source,id,lexeme
<survey_name>,<survey_item_id>,<concept_gloss>
<survey_name>,<survey_item_id>,<concept_gloss>
```

### Generic example

```csv
source,id,lexeme
SurveyA,001,water
SurveyA,002,fire
SurveyA,003,eat
SurveyB,A-10,water
SurveyB,A-20,fire
SurveyB,A-30,eat
SurveyC,4.1,water
SurveyC,4.2,fire
```

This tells PARSE that:

- `SurveyA` item `001`, `SurveyB` item `A-10`, and `SurveyC` item `4.1` all mean `water`.
- `SurveyA` item `002`, `SurveyB` item `A-20`, and `SurveyC` item `4.2` all mean `fire`.
- `SurveyA` item `003` and `SurveyB` item `A-30` both mean `eat`.

The exact survey names and item IDs are yours. The important rule is that the same `lexeme` text must be used for rows that describe the same concept.

## Matching rules in plain language

The tool compares your reference CSV against the workspace's existing `concepts.csv`.

For each PARSE concept, it checks:

1. Does the concept's `concept_en` gloss appear in the reference CSV?
2. Does the reference CSV include the concept's current primary survey and item ID?
3. Are there other surveys in the reference CSV with the same gloss?

If all three are true, the tool can add those other survey IDs as alternates.

### Example of a safe match

Suppose a row in PARSE's `concepts.csv` says:

```csv
id,concept_en,source_item,source_survey,custom_order
1,water,001,SurveyA,1
```

Your reference CSV should include the current primary row plus the alternate rows:

```csv
source,id,lexeme
SurveyA,001,water
SurveyB,A-10,water
SurveyC,4.1,water
```

The dry run will propose adding `SurveyB` item `A-10` and `SurveyC` item `4.1` as alternate survey IDs for the existing `water` concept. It will not change `concepts.csv` during population.

### Common formatting mistakes

| Problem | Why it matters | Fix |
|---|---|---|
| Missing `source`, `id`, or `lexeme` column | The tool ignores rows without all three values. | Add the required columns exactly, or with different capitalization only. |
| A survey item ID is changed by spreadsheet formatting | IDs like `001` can become `1`; IDs like `4.10` can become `4.1`. | Format the ID column as text before saving the CSV. |
| The reference CSV omits the current primary survey row | PARSE cannot prove the alternate rows belong to the same existing concept. | Include the current primary survey/item row and every alternate survey/item row for that gloss. |
| The same survey and gloss appears twice with different IDs | PARSE cannot know which ID is correct. | Deduplicate the reference CSV before running the tool. |
| `lexeme` contains full language forms instead of glosses | The tool matches concepts by `concept_en`, not by speaker responses. | Use stable concept glosses such as `water`, `fire`, or your project's existing `concept_en` labels. |

## MCP tool usage

Tool name:

```text
populate_cross_survey_links
```

Parameters:

| Parameter | Required | What it means |
|---|---|---|
| `referencePath` | yes | Path to the reference CSV. Use an absolute path or a path relative to the PARSE workspace. |
| `dryRun` | yes | `true` previews the result without writing. `false` applies the safe proposed links. |
| `singleWordOnly` | no | Defaults to `true`. When true, PARSE only auto-links simple one-word concept labels and skips concept labels with spaces, commas, or parentheses. |

### Step 1: dry run first

Ask the MCP tool to preview the links:

```jsonc
{
  "name": "populate_cross_survey_links",
  "arguments": {
    "referencePath": "imports/concept-reference.csv",
    "dryRun": true,
    "singleWordOnly": true
  }
}
```

Read the dry-run result before applying anything:

| Result field | Meaning |
|---|---|
| `matched` | Concepts found in both PARSE and your reference CSV. |
| `would_add` | Links PARSE would add if you apply the run. This is the main list to review. |
| `conflicts` | Rows PARSE did not trust. Fix these in the CSV or workspace before applying. |
| `skipped_multiword` | Concepts skipped because `singleWordOnly` is true. |

A useful dry-run result should have the expected concepts in `would_add` and no surprising entries in `conflicts`.

### Step 2: apply after review

When the dry run looks correct, run the same tool with `dryRun: false`:

```jsonc
{
  "name": "populate_cross_survey_links",
  "arguments": {
    "referencePath": "imports/concept-reference.csv",
    "dryRun": false,
    "singleWordOnly": true
  }
}
```

Applying the tool writes the alternate links to `survey-overlap.json`. It does not rewrite `concepts.csv` and does not change speaker annotations.

## What PARSE stores

PARSE uses two workspace files together:

| File | User-facing role |
|---|---|
| `concepts.csv` | The main concept list. Each concept has one current primary survey and item ID. Exports use this primary value. |
| `survey-overlap.json` | PARSE-managed sidecar file for alternate survey IDs and per-speaker survey preferences. You usually do not edit this by hand. |

After population, a concept can have one primary survey ID in `concepts.csv` and one or more alternate survey IDs in `survey-overlap.json`.

## What changes in the UI

After the links are applied:

- Concepts with only one survey ID show a normal static survey badge.
- Concepts with multiple survey IDs show a clickable badge.
- With a speaker active, clicking the badge changes that speaker's preferred survey ID for the concept. This is non-destructive and does not rewrite `concepts.csv`.
- Without a speaker active, clicking the badge can promote another survey ID to the global primary value. PARSE backs up `concepts.csv` before rewriting it.

Use promotion only when you want exports to use a different survey's IDs as the primary IDs.

## End-to-end workflow

1. **Prepare your reference CSV.** Use the required `source,id,lexeme` columns. Include one row per survey item you want PARSE to know about.
2. **Check the glosses.** The `lexeme` values should match the `concept_en` labels in PARSE's `concepts.csv`.
3. **Place the CSV where PARSE can read it.** A workspace-relative path such as `imports/concept-reference.csv` is easiest.
4. **Run the MCP dry run.** Use `dryRun: true` and inspect `would_add`, `conflicts`, and `skipped_multiword`.
5. **Fix the CSV if needed.** Resolve duplicate IDs, missing primary rows, spelling differences, or spreadsheet formatting issues.
6. **Apply the links.** Re-run with `dryRun: false` only after the preview is correct.
7. **Verify in PARSE.** Open the concept list and check that linked concepts now show clickable survey badges.
8. **Promote only if needed.** If an export should use another survey's IDs as primary, promote that survey in the UI before exporting.

## Troubleshooting

**The tool says there are no `would_add` rows.** Check that the `lexeme` values in the reference CSV match the `concept_en` values in `concepts.csv`. Also check that the current primary survey/item row is present in the reference CSV.

**Rows appear under `conflicts`.** PARSE found something it could not safely link. Common causes are duplicate survey/gloss rows with different IDs, a current primary ID that disagrees with `concepts.csv`, or an existing sidecar entry with a different item ID.

**IDs changed after saving the CSV.** Spreadsheet tools often strip leading zeros or change decimals. Reopen the CSV as plain text and verify the `id` column. If needed, set the spreadsheet column type to text and export again.

**Multi-word concepts are skipped.** This is expected when `singleWordOnly` is true. You can set `singleWordOnly: false`, but review the dry run carefully because longer labels are more likely to represent variants rather than exact duplicates.

**The badge is not clickable.** The concept probably has only one linked survey ID. Re-run the dry run and confirm that the concept appears in `would_add` or is already linked in the workspace.

**Exports still use the old survey ID.** Exports use the primary value in `concepts.csv`. Promote the desired survey ID to primary before exporting.

## Advanced: optional CLI equivalent

Most users should use the MCP tool. If you are running the script manually from a terminal, the equivalent dry run is:

```bash
PYTHONPATH=python python3 scripts/populate_cross_survey_links.py \
  --reference imports/concept-reference.csv \
  --workspace /path/to/parse-workspace
```

To apply the result, add `--apply` after reviewing the dry run:

```bash
PYTHONPATH=python python3 scripts/populate_cross_survey_links.py \
  --reference imports/concept-reference.csv \
  --workspace /path/to/parse-workspace \
  --apply
```
