# export_beast2_xml

**Category:** Export
**Mutability:** mutating (writes a BEAST2 `.xml` inside the project)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium

## One-Sentence Summary
Export a runnable BEAST2 (v2.7) XML analysis from the cognate-character matrix, so PARSE data can go straight into BEAST2 with no BEAUti step and no external script.

## When to Use
- Producing a ready-to-run BEAST2 analysis from a workspace's committed cognate decisions.
- Closing the last leg of the phylogenetic pipeline: `export_nexus` gives the matrix; this gives the runnable analysis.
- Thesis-tag runs: pair with `conceptTag` to fold survey-overlap duplicates and scope to a concept list.

## When NOT to Use
- When you only need the character matrix (use `export_nexus`).
- For a tuned study design. The template is a sensible *default* (binary substitution model, Yule tree prior, strict clock, fixed rates/clock, estimated frequencies). Refine the model in BEAUti/by hand for a real analysis.

## Parameters

| Parameter   | Type    | Required | Description | Default | Example |
|-------------|---------|----------|-------------|---------|---------|
| outputPath  | string  | No  | Project-relative or absolute path inside project root. Omit for preview. | (preview only) | `"exports/beast2/analysis.xml"` |
| conceptTag  | string  | No  | Restrict to a concept tag and fold survey-overlap duplicate concept ids into one canonical character. | (none) | `"custom-sk-concept-list"` |
| consolidate | boolean | No  | Fold survey-overlap duplicate concept ids (implied when `conceptTag` is set). | `false` | `true` |
| chainLength | integer | No  | MCMC chain length; loggers sample ~200 times across the chain. | `200000` | `1000000` |
| dryRun      | boolean | No  | Preview only — never writes. | `false` | `true` |

## Expected Output
- Preview (`dryRun` or no `outputPath`): `{ preview (first 2000 chars), totalChars, chainLength, beast2_ready, warnings, note }`, plus `consolidated`/`consolidation` when consolidating.
- Write: `{ success: true, outputPath, totalChars, chainLength, ... }`.

The emitted XML uses `$(filebase)` for log/tree filenames, so outputs are named after the XML basename (e.g. `analysis.log`, `analysis.trees`).

## Running the result
```
beast analysis.xml                 # runs the MCMC -> analysis.log + analysis.trees
treeannotator -burnin 10 analysis.trees analysis.mcc.tree
```

## Common Failure Modes & How to Recover

| Failure | Symptom | Recovery |
|---|---|---|
| Empty / uninformative analysis | `beast2_ready: false`, all-zero COGID warning | No committed cognate decisions; commit them, then re-export. |
| Unknown `conceptTag` | `"matched 0 concepts"` warning, empty matrix | Check the tag id (`list_concepts_by_tag`). |
| BEAST2 rejects the XML | Parser error on load | Confirm BEAST2 is v2.7.x; this template targets the 2.7 namespace/spec set. |
