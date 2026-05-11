# contact_lexeme_lookup

**Category:** Comparison
**Mutability:** mutating (writes `config/sil_contact_languages.json`)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Medium–High
**Estimated Tokens:** ~290 (short) / ~620 (full)

## One-Sentence Summary
Fetches reference IPA forms for contact/comparison languages from third-party sources (local CLDF, ASJP, Wikidata, Wiktionary, Grok LLM, literature) and merges them into `config/sil_contact_languages.json` — gated by mandatory `dryRun`.

## When to Use
- Bootstrapping contact-language reference forms for a new project (e.g. Arabic, Persian, Central Kurdish forms to compare against Southern Kurdish data).
- Filling gaps in existing contact-language coverage — `overwrite: false` (default) is non-destructive.
- Refreshing entries when a provider chain order changes or a new provider becomes preferred.
- Bounded previews for cost / quality control via `maxConcepts`.

## When NOT to Use
- Without a `dryRun: true` first. The `dryRun` parameter is *required* by schema — the catalog gates this tool explicitly so callers don't accidentally hit external providers and overwrite the contact-languages file.
- For pure preview without provider calls. `dryRun: true` does still go out to providers (it just doesn't write). For "what's already in the file?", read it directly via `read_text_preview` (Project bucket).
- To replace existing forms accidentally — `overwrite: false` is the default. Only flip to `true` when the user has explicitly confirmed they want to re-fetch.
- For local-only comparison without external lookups — this tool's purpose is the third-party provider chain. If you only want cognate similarity from existing data, use `cognate_compute_preview`.

## Parameters

| Parameter   | Type     | Required | Description                                                                                                       | Default                       | Example               |
|-------------|----------|----------|-------------------------------------------------------------------------------------------------------------------|-------------------------------|-----------------------|
| dryRun      | boolean  | Yes      | `true` previews (provider chain runs but no write); `false` writes results into `sil_contact_languages.json`.     | —                             | `true`                |
| languages   | string[] | No       | ISO 639 codes.                                                                                                    | —                             | `["ar", "fa", "ckb"]` |
| conceptIds  | string[] | No       | Project concept IDs or English labels.                                                                            | (all project concepts)        | `["water", "fire"]`   |
| providers   | string[] | No       | Provider priority order. Names from the project's provider registry.                                              | (full chain default)          | `["cldf", "wiktionary", "grok"]` |
| maxConcepts | integer  | No       | Cap on concepts processed. `minimum=1`, `maximum=200`.                                                            | —                             | `25`                  |
| overwrite   | boolean  | No       | If `true` and `dryRun: false`, re-fetch even when forms already exist. Ignored when `dryRun: true`.               | `false`                       | `false`               |

## Expected Output
On `dryRun: true`: returns the candidate forms per (language, conceptId), the provider that produced each, and a count of how many would be merged vs. skipped (because they already exist) — without touching the file.

On `dryRun: false`: writes the merged results into `config/sil_contact_languages.json` and returns `{ ok: true, languagesUpdated, conceptsUpdated, providersUsed, ... }`. The previous file content is not automatically backed up.

## Example Successful Call
Dry run (mandatory first step):
```json
{
  "languages": ["ar", "fa"],
  "conceptIds": ["water", "fire", "stone"],
  "providers": ["cldf", "wiktionary", "grok"],
  "maxConcepts": 25,
  "dryRun": true
}
```

Live apply after confirmation:
```json
{
  "languages": ["ar", "fa"],
  "conceptIds": ["water", "fire", "stone"],
  "providers": ["cldf", "wiktionary", "grok"],
  "maxConcepts": 25,
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                                | Recovery                                                                                              |
|------------------------------------------|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Missing provider credentials             | Provider returns errors / empty results in the chain                   | Check provider setup; remove the failing provider from `providers` or fall back to the default chain. |
| Bad form transcribed by a provider       | Forms look implausible for the language                                | Adjust `providers` priority (e.g. prefer `cldf` / `wiktionary` over `grok` for known languages).      |
| Existing forms not refreshed             | Live apply completes but some entries unchanged                        | Default `overwrite: false`. Re-run with `overwrite: true` only if the user explicitly wants re-fetch.  |
| Exceeded `maxConcepts` quietly           | Only a subset of `conceptIds` processed                                | The cap silently bounds the call. Increase `maxConcepts` (up to 200) or run in batches.               |
| Unknown concept labels                   | Empty results for those concepts                                       | Verify via `project_context_read` (`concepts`); use canonical IDs rather than English labels for stability. |

## Agent Reasoning Notes
This is the only path PARSE has for *fetching* contact-language data; without it, comparison against Arabic, Persian, etc. relies on whatever's already in the file. Treat the mandatory `dryRun` as load-bearing — always preview first, present the candidate forms to the user, and only `dryRun: false` after confirmation. The provider chain has different quality profiles: CLDF and Wikidata for citable references, Wiktionary for breadth, Grok for fallback when nothing else has the concept. Pair with `cognate_compute_preview` (consumes the file this writes) and `enrichments_write` (persists cognate decisions that use this data).

## Related Skills
- `cognate_compute_preview` — consumes `sil_contact_languages.json` for cross-language similarity.
- `read_text_preview` (Project bucket) — inspect existing contact-languages file content.
- `clef_clear_data` (Project bucket) — destructive cleanup of CLEF-populated entries (use with care).
- `enrichments_write` (Project bucket) — persist downstream cognate / borrowing decisions.
