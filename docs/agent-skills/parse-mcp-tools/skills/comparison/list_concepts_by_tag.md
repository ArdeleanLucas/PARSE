# list_concepts_by_tag

**Category:** Comparison
**Mutability:** read_only
**Supports Dry Run:** N/A (preview by design)
**Complexity:** Low
**Estimated Tokens:** ~220 (short) / ~470 (full)

## One-Sentence Summary
Resolves a tag query (`ANY` / `ALL` semantics over `tagLabels`) and returns matched concepts per speaker — without running any STT or IPA work. The canonical dry-run preview before `rerun_lexemes_by_tag`.

## When to Use
- Before `rerun_lexemes_by_tag` — always. This is the no-cost preview that confirms the tag query resolves to the expected concept set before kicking off a GPU rerun.
- For tag-driven discovery: "which concepts have the `loanword` tag across these speakers?".
- To validate tag-vocabulary changes: after editing the tag store, run this to see what the query now matches.

## When NOT to Use
- To actually rerun ORTH/IPA — that's `rerun_lexemes_by_tag` (the matching write/compute path).
- For all concepts (no tag filter) — use `project_context_read` (Project bucket) to enumerate concepts and speakers.
- For tag-vocabulary inspection only ("what tags exist on this project?") — read `parse-tags.json` directly via `read_text_preview` (Project bucket) or `enrichments_read` if tags live there.

## Parameters

| Parameter | Type     | Required | Description                                                                                              | Default | Example                              |
|-----------|----------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| speakers  | oneOf    | Yes      | Either an array of speaker IDs or `"all"`.                                                              | —       | `["Khan01", "Khan02"]` or `"all"`    |
| tagLabels | string[] | Yes      | One or more tag labels to match.                                                                         | —       | `["loanword", "uncertain"]`          |
| match     | string   | No       | `any` = union (concept needs at least one of the tags); `all` = intersection (concept needs every tag). | `"any"` | `"all"`                              |

**ANY vs ALL semantics:**
- `any` — A concept is included if it carries **at least one** of the selected tags. Use for broad discovery / batching.
- `all` — A concept is included only if it carries **every** selected tag. Use for precise filtering.

## Expected Output
Returns `{ readOnly, match, speakers: [{ speaker, conceptIds: ["..."], count }], totalConceptsMatched, ... }`. Each speaker entry lists matched concept IDs.

Does not mutate project state.

## Example Successful Call
ANY across two speakers:
```json
{
  "speakers": ["Khan01", "Khan02"],
  "tagLabels": ["loanword", "uncertain"],
  "match": "any"
}
```

ALL across the whole project:
```json
{
  "speakers": "all",
  "tagLabels": ["loanword", "high_confidence"],
  "match": "all"
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Unknown tag label                      | Tool returns ambiguous-tag error                                     | Verify tag labels against `parse-tags.json` (via `read_text_preview` or `enrichments_read`). Typos and case mismatch are common. |
| Ambiguous tag label                    | Tool returns ambiguous-tag error (multiple tags share the label)     | Use canonical tag IDs instead of labels, or rename one of the ambiguous tags in `parse-tags.json`.    |
| Empty result with `match: "all"`       | `totalConceptsMatched: 0`                                            | The intersection is empty. Switch to `match: "any"` for broader matches, or drop a tag from `tagLabels`. |
| Tag covers nothing across speakers     | All speakers report `count: 0`                                       | The tag may exist in vocabulary but be unused. Verify with `enrichments_read` / tag-store inspection. |

## Agent Reasoning Notes
Use `list_concepts_by_tag` as the always-on pre-flight before `rerun_lexemes_by_tag` — they share the exact same `(speakers, tagLabels, match)` resolution semantics. Run this first, present the matched concept set to the user, and only after confirmation run the compute path. This preview-first discipline is especially important because the matching rerun consumes GPU time and acquires per-speaker locks.

## Related Skills
- `rerun_lexemes_by_tag` — same query semantics, runs ORTH/IPA over the matched concepts.
- `enrichments_read`, `read_text_preview` — inspect the tag vocabulary in `parse-tags.json`.
- `project_context_read` — enumerate speakers and concepts unfiltered.
