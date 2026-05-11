# prepare_tag_import

**Category:** Project
**Mutability:** mutating (creates / updates a tag in `parse-tags.json`)
**Supports Dry Run:** Yes (`dryRun` is required)
**Complexity:** Low–Medium
**Estimated Tokens:** ~210 (short) / ~450 (full)

## One-Sentence Summary
Creates or updates a tag with an explicit list of concept IDs and writes it to `parse-tags.json` — the curated-input alternative to CSV-based `import_tag_csv` when the agent already knows exactly which concepts to tag.

## When to Use
- Programmatically creating a tag from a known list of concept IDs (e.g. after a query, after computing a candidate set).
- Updating an existing tag's concept list — same name, different IDs.
- For tag creation without CSV ingestion / fuzzy matching.
- When the agent has already filtered the concept population and wants to persist that subset as a named tag.

## When NOT to Use
- For CSV-driven tag creation — use `import_tag_csv` (handles fuzzy matching, label normalization, two-phase dry-run-then-name flow).
- Without `dryRun: true` first. The schema requires `dryRun` — preview the tag content before persisting.
- For tag *removal*. There's no delete operation here; remove tag entries via direct file edit of `parse-tags.json`.

## Parameters

| Parameter           | Type     | Required | Description                                                                                  | Default | Example                  |
|---------------------|----------|----------|----------------------------------------------------------------------------------------------|---------|--------------------------|
| tagName             | string   | Yes      | Tag identifier. `minLength=1`, `maxLength=100`.                                              | —       | `"high_priority"`        |
| conceptIds          | string[] | Yes      | Explicit concept IDs to include in the tag.                                                  | —       | `["12", "13", "14"]`     |
| color               | string   | No       | Tag color hex.                                                                                | —       | `"#FFB200"`              |
| propagateToSpeakers | boolean  | No       | When `true`, propagate the tag to every speaker's row for matched concepts.                  | `true`  | `true`                   |
| dryRun              | boolean  | Yes      | `true` previews; `false` writes.                                                              | —       | `true`                   |

## Expected Output
On `dryRun: true`: returns `{ readOnly, tagName, conceptIds, color, propagateToSpeakers, action }` — the planned tag entry without writing.

On `dryRun: false`: writes the tag to `parse-tags.json` and returns `{ ok: true, tagName, conceptIds, action }` (`action` ∈ `"created"`, `"updated"`).

## Example Successful Call
Dry run:
```json
{
  "tagName": "high_priority",
  "conceptIds": ["12", "13", "14"],
  "color": "#FFB200",
  "dryRun": true
}
```

Live apply:
```json
{
  "tagName": "high_priority",
  "conceptIds": ["12", "13", "14"],
  "color": "#FFB200",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                              |
|------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Existing tag overwritten silently        | Live apply replaced a same-named tag's concept list                  | Read `parse-tags.json` first via `read_text_preview`; rename or version if collision is a concern.    |
| Unknown concept IDs                      | Tag created but downstream lookups (`list_concepts_by_tag`) return less than expected | Verify IDs against `project_context_read` (`concepts` block) before creating.                  |
| Propagation surprises                    | `propagateToSpeakers: true` (default) wrote tag onto every speaker — including ones you didn't want | Set `propagateToSpeakers: false` for tag-on-concept-only without per-speaker propagation. |
| Forgot `dryRun`                          | Validation error                                                     | `dryRun` is required by schema. Always preview first.                                                  |

## Agent Reasoning Notes
This is the curated-input tag-creation path; `import_tag_csv` is the CSV-driven counterpart. The two end up in the same `parse-tags.json` file with the same shape, but the source-of-truth for the concept list is different (explicit array vs. fuzzy-matched CSV rows). For agent workflows where you compute a candidate set and want to persist it, this is the right tool. For human-authored CSVs from external classifications, `import_tag_csv` handles the matching for you.

## Related Skills
- `import_tag_csv` — CSV-driven counterpart with fuzzy matching.
- `list_concepts_by_tag` (Comparison bucket) — verify the tag matched the expected concepts after creation.
- `rerun_lexemes_by_tag` (Comparison bucket) — downstream consumer of tags.
- `read_text_preview` — inspect existing `parse-tags.json` before writing.
- `project_context_read` — verify concept IDs before tag creation.
