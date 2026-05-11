# cognate_compute_preview

**Category:** Comparison
**Mutability:** read_only
**Supports Dry Run:** N/A (preview-only by design)
**Complexity:** Medium
**Estimated Tokens:** ~230 (short) / ~500 (full)

## One-Sentence Summary
Computes a read-only cognate/similarity preview from current annotations — does *not* write `parse-enrichments.json` — useful for inspecting candidate cognate groups before committing decisions.

## When to Use
- Exploring potential cognate sets across speakers without persisting anything.
- Tuning the similarity `threshold` to find the value that yields a good set/grouping for a given language pair.
- Previewing how `contactLanguages` reference forms would influence the grouping (without fetching them — just including their existing entries in the comparison).
- Pre-flight before the user manually edits cognate sets in the UI or via `enrichments_write` (Project bucket).

## When NOT to Use
- To *persist* cognate decisions. This tool is preview-only; durable cognate sets live in `parse-enrichments.json` and are written through the UI compare-mode flow or direct enrichments edits, not through this tool.
- For full compare-mode rendering — use `prepare_compare_mode` to get the full bundle (annotations + cognate preview + cross-speaker matches in one structured response).
- For fetching contact-language reference forms — that's `contact_lexeme_lookup`. This tool *consumes* whatever's already in `sil_contact_languages.json`.
- For very large projects without bounding. Use `maxConcepts` to cap the preview; the default may be slower than expected on large corpora.

## Parameters

| Parameter         | Type     | Required | Description                                                                                  | Default   | Example                  |
|-------------------|----------|----------|----------------------------------------------------------------------------------------------|-----------|--------------------------|
| speakers          | string[] | No       | Restrict to these speakers. Omit for all.                                                    | (all)     | `["Khan01", "Khan02"]`   |
| conceptIds        | string[] | No       | Restrict to these concept IDs. Omit for all.                                                 | (all)     | `["12", "13", "14"]`     |
| threshold         | number   | No       | Similarity threshold for grouping. `minimum=0.01`, `maximum=2.0`.                            | (server default) | `0.7`             |
| contactLanguages  | string[] | No       | Include forms from these contact-language entries from `sil_contact_languages.json`.         | —         | `["ar", "fa"]`           |
| includeSimilarity | boolean  | No       | If `true`, return per-pair similarity scores in addition to the grouping.                    | `false`   | `true`                   |
| maxConcepts       | integer  | No       | Cap on concepts processed. `minimum=1`, `maximum=500`.                                       | (server default) | `100`             |

## Expected Output
Returns `{ readOnly, groups: [...], scores?: [...], conceptsProcessed, speakersConsidered, contactLanguagesUsed, threshold, ... }`. Each `groups` entry is a candidate cognate set (collection of `(speaker, conceptId)` pairs that the similarity computation grouped together). `scores` (only when `includeSimilarity: true`) carries per-pair similarity values.

Does not mutate project state.

## Example Successful Call
```json
{
  "speakers": ["Khan01", "Khan02", "Khan03"],
  "conceptIds": ["12", "13", "14"],
  "threshold": 0.7,
  "contactLanguages": ["ar", "fa"],
  "includeSimilarity": true,
  "maxConcepts": 100
}
```

## Common Failure Modes & How to Recover

| Failure                              | Symptom                                                            | Recovery                                                                                              |
|--------------------------------------|--------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Empty groups (threshold too strict)  | `groups: []`                                                       | Lower `threshold`. Default is calibrated for typical Kurdish data; corpus-specific tuning may be needed.|
| Too many tiny groups                 | Many single-member groups in `groups`                              | Raise `threshold`. Or restrict scope via `speakers` / `conceptIds`.                                   |
| Contact language entries missing      | Few/no contact rows in groupings despite specifying `contactLanguages` | Run `contact_lexeme_lookup` to populate `sil_contact_languages.json` first.                       |
| Slow on large projects               | Long latency                                                       | Add `maxConcepts` to bound. Or scope down with `conceptIds` / `speakers`.                             |

## Agent Reasoning Notes
This is the cheap explore-and-tune path for cognate review — fast, no writes, repeat with different `threshold` values until the grouping looks right, then have a human commit decisions through the UI. Pair with `phonetic_rules_apply` (Annotation bucket) when normalizing IPA before comparison matters, and with `contact_lexeme_lookup` to populate reference forms before this preview. For one-shot "give me the compare-mode bundle for this concept range", reach for `prepare_compare_mode` instead — it wraps this tool together with `cross_speaker_match_preview` and the annotation load.

## Related Skills
- `prepare_compare_mode` — workflow-level compare bundle that includes this preview.
- `contact_lexeme_lookup` — populate `sil_contact_languages.json` before including reference forms.
- `cross_speaker_match_preview` — STT-driven cross-speaker matches (complementary signal).
- `phonetic_rules_apply` — normalize IPA before comparison.
- `enrichments_read`, `enrichments_write` (Project bucket) — read/persist cognate decisions.
