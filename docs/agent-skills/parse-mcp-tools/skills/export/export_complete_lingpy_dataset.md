# export_complete_lingpy_dataset

**Category:** Export
**Mutability:** mutating workflow (writes LingPy TSV + NEXUS under `exports/lingpy/`; optional contact-lexeme refresh)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium
**Estimated Tokens:** ~260 (short) / ~570 (full)

## One-Sentence Summary
Exports a complete PARSE phylogenetics bundle — LingPy TSV + NEXUS character matrix under `exports/lingpy/` — by chaining the existing low-level export tools, with optional contact-lexeme refresh as a first stage.

## When to Use
- Producing a ready-to-ship LingPy + NEXUS bundle for downstream phylogenetic analysis (BEAST2, LingPy, LexStat).
- Combining `contact_lexeme_lookup` + `export_lingpy_tsv` + `export_nexus` in one call when those three steps are always run together.
- Thesis-export workflow: the final step before handing data off to phylogenetics tooling.

## When NOT to Use
- For TSV-only or NEXUS-only exports — call `export_lingpy_tsv` or `export_nexus` directly. The workflow's overhead is only worth it when you actually want both.
- For per-stage parameter tuning — the workflow wraps the underlying tools with defaults. For custom thresholds on `cognate_compute_preview` or `contact_lexeme_lookup`, call those tools individually first, then run the unbundled exports.
- Without first verifying enrichments. The workflow assumes `parse-enrichments.json` has enough cognate data; if cognate decisions haven't been made, the export will be empty or partial.
- For arbitrary file destinations. The workflow writes to `exports/lingpy/wordlist.tsv` and `exports/lingpy/dataset.nex` — fixed paths.

## Parameters

| Parameter            | Type    | Required | Description                                                                       | Default | Example  |
|----------------------|---------|----------|-----------------------------------------------------------------------------------|---------|----------|
| with_contact_lexemes | boolean | No       | If `true`, run `contact_lexeme_lookup` as a first stage before TSV / NEXUS export. | `false` | `true`   |
| dryRun               | boolean | No       | If `true`, preview the bundle and planned artifacts without writing files.        | `false` | `true`   |

## Expected Output
On `dryRun: true`: returns the planned artifact paths (`exports/lingpy/wordlist.tsv`, `exports/lingpy/dataset.nex`) and a per-stage preview from each underlying tool (`export_lingpy_tsv`, `export_nexus`, optional `contact_lexeme_lookup`). The response shape includes `stages: [{ stage, tool, status: "preview", payload }, ...]`.

On `dryRun: false`: runs each stage live, writes the TSV and NEXUS files, and returns `{ ok: true, artifacts: {lingpy_tsv, nexus}, stages, final_status: "complete", exported_at }`.

## Example Successful Call
Dry run without contact refresh:
```json
{
  "with_contact_lexemes": false,
  "dryRun": true
}
```

Live export with contact-lexeme refresh:
```json
{
  "with_contact_lexemes": true,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Empty / partial exports                | Output files exist but row counts are low                            | Cognate enrichments insufficient. Use `cognate_compute_preview` to inspect grouping; commit decisions before re-exporting. |
| Contact-lexeme stage fails             | `with_contact_lexemes: true` errors at first stage                   | Run `contact_lexeme_lookup` standalone to diagnose provider issues, then re-run the workflow.         |
| `exports/lingpy/` files overwritten    | Prior bundle replaced                                                | No auto-backup. Snapshot or rename the prior bundle if you need to keep it.                           |
| Workflow halts mid-chain                | `final_status` != `complete`                                         | Inspect `stages` for the failed stage's payload — that's the failure point.                            |

## Agent Reasoning Notes
This is the canonical thesis-export endpoint when both TSV and NEXUS are needed. The `with_contact_lexemes: true` mode is for cases where the contact-language reference forms have changed since the last cognate analysis — it re-fetches before exporting so the NEXUS matrix reflects current third-party data. For one-off TSV-only or NEXUS-only exports, the underlying tools (`export_lingpy_tsv`, `export_nexus`) are cheaper and clearer. Always dry-run first on a fresh project to verify the bundle shape before committing the live write.

## Related Skills
- `export_lingpy_tsv` — direct call for TSV-only export.
- `export_nexus` — direct call for NEXUS-only export.
- `contact_lexeme_lookup` (Comparison bucket) — the optional first stage; can be run independently first.
- `cognate_compute_preview` (Comparison bucket) — inspect cognate grouping before exporting.
- `enrichments_read` (Project bucket) — verify cognate decisions are in `parse-enrichments.json`.
