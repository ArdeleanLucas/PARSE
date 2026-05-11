# clef_clear_data

**Category:** Project
**Mutability:** mutating (rewrites `config/sil_contact_languages.json`; optionally clears provider caches)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Low–Medium
**Estimated Tokens:** ~220 (short) / ~470 (full)

## One-Sentence Summary
Clears CLEF-populated reference forms from `config/sil_contact_languages.json` — supports `dryRun` preview, optional `languages`/`concepts` scoping, and optional provider-cache cleanup via `clearCache`.

## When to Use
- Resetting CLEF-fetched contact-language data when results have gone stale or wrong (bad provider output, schema change, etc.).
- Selective cleanup — scope by `languages` or `concepts` arrays to clear only specific entries.
- Cache invalidation: pair with `clearCache: true` when stale provider cache entries are also a problem.
- Before a fresh `contact_lexeme_lookup` run when you want clean state rather than merging onto existing data.

## When NOT to Use
- Without `dryRun: true` first. This tool is destructive — always preview the planned clear scope before committing.
- For non-CLEF entries. The tool clears CLEF-populated forms specifically; manually-entered or hand-edited contact-language data outside the CLEF flow may be affected too, so audit the file with `read_text_preview` first.
- For full-file replacement. Use direct file editing via your normal workflow if you need to rebuild `sil_contact_languages.json` from scratch.

## Parameters

| Parameter   | Type     | Required | Description                                                                                  | Default | Example                |
|-------------|----------|----------|----------------------------------------------------------------------------------------------|---------|------------------------|
| dryRun      | boolean  | No       | If `true`, preview the count of forms / languages / concepts / cache entries to clear without writing. | `false` | `true`                 |
| languages   | string[] | No       | Language codes to clear. Omit or pass `null` to clear all configured languages.              | (all)   | `["ar", "fa"]`         |
| concepts    | string[] | No       | Concept labels to clear. Omit or pass `null` to clear all concepts.                          | (all)   | `["water", "fire"]`    |
| clearCache  | boolean  | No       | If `true`, also remove CLEF provider caches under `config/cache`.                            | `false` | `true`                 |

## Expected Output
On `dryRun: true`: returns `{ readOnly, formsToClear, languagesAffected, conceptsAffected, cacheEntriesToClear }` — the planned scope without modifying anything.

On `dryRun: false`: rewrites `config/sil_contact_languages.json` and (if `clearCache: true`) removes cache files. Returns `{ ok: true, formsCleared, languagesAffected, conceptsAffected, cacheEntriesCleared }`.

## Example Successful Call
Preview clearing all CLEF data:
```json
{
  "dryRun": true
}
```

Scoped clear of two languages with cache cleanup:
```json
{
  "languages": ["ar", "fa"],
  "clearCache": true,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Cleared more than intended             | Live apply removed unexpected entries                                | No auto-rollback. Snapshot `config/sil_contact_languages.json` before destructive clears (or rely on git). |
| Cache not actually cleared             | `clearCache: true` but caches persist                                | Provider cache locations may differ from what the tool expects. Inspect `config/cache/` directly via `read_text_preview`. |
| Selective scope missed entries         | `languages` / `concepts` filter excluded what you wanted             | Re-run with broader scope, or omit the filter to clear all.                                           |
| Mixed CLEF / manual entries            | Manually-edited contact-language data also affected                  | This tool clears CLEF-populated forms; hand-edited entries may not be distinguishable. Audit with `read_text_preview` before clearing. |

## Agent Reasoning Notes
This is the cleanup half of the CLEF / `contact_lexeme_lookup` flow. The mandatory dry-run discipline matches `contact_lexeme_lookup`'s — both deal with the same `sil_contact_languages.json` file and both can affect data agents/users care about. Rely on git for true rollback; the tool doesn't auto-backup. Pair with `read_text_preview` to inspect the file before and after, and with `contact_lexeme_lookup` (Comparison bucket) to repopulate after clearing.

## Related Skills
- `contact_lexeme_lookup` (Comparison bucket) — the canonical write path for this file.
- `read_text_preview` — inspect `sil_contact_languages.json` before / after clearing.
- `enrichments_read` — separately inspect cognate data that may reference the cleared forms.
