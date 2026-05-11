# rerun_lexemes_by_tag

**Category:** Comparison
**Mutability:** read_only response, but consumes GPU and acquires per-speaker locks; does NOT persist rerun output to annotations
**Supports Dry Run:** No (use `list_concepts_by_tag` as the preview instead)
**Complexity:** Medium–High
**Estimated Tokens:** ~290 (short) / ~620 (full)

## One-Sentence Summary
Synchronously runs ORTH and/or IPA over every concept window matched by a tag query (across selected speakers), returning the rerun text per `(speaker, conceptId, field)` — for surfacing what the model would *now* say without persisting it to annotations.

## When to Use
- Comparing the live ORTH/IPA model against existing annotations on tagged concepts (e.g. concepts tagged `uncertain` or `revisit`).
- Quick "what would the model say now?" check after a model upgrade or rule change, scoped by tag to avoid wasting GPU on the whole corpus.
- Pairs naturally after `list_concepts_by_tag` — preview the resolved concept set, then rerun.
- Synchronous: returns when done. No `jobId` polling.

## When NOT to Use
- To persist the rerun output. The tool does NOT write back to annotations — it returns the text. To persist, edit annotations manually or run the standard pipeline tools.
- Without `list_concepts_by_tag` first. This tool refuses ambiguous tag labels (`409`) and refuses `match: "all"` if any label is unknown or ambiguous (`400`) — surface those to the user instead of running GPU on the wrong concept set.
- For unscoped reruns across the whole project. Pass concrete `tagLabels`. Tag-driven scoping is the entire point.
- For full annotation pipeline runs — use `pipeline_run` / `run_full_annotation_pipeline` (Advanced bucket). This tool is per-concept-window, not per-tier.

## Parameters

| Parameter | Type     | Required | Description                                                                                  | Default | Example                              |
|-----------|----------|----------|----------------------------------------------------------------------------------------------|---------|--------------------------------------|
| speakers  | oneOf    | Yes      | Either an array of speaker IDs or `"all"`.                                                  | —       | `["Khan01", "Khan02"]` or `"all"`    |
| tagLabels | string[] | Yes      | One or more tag labels to match.                                                             | —       | `["uncertain"]`                      |
| match     | string   | No       | `any` (union) or `all` (intersection). See `list_concepts_by_tag` for full semantics.        | `"any"` | `"any"`                              |
| field     | string   | Yes      | Which field to rerun: `ipa`, `ortho`, or `both`.                                              | —       | `"both"`                             |
| pad       | number   | No       | Padding around each concept window in seconds. Enum: `0.0`, `0.2`, `0.5`.                    | `0.2`   | `0.2`                                |

## Expected Output
Returns `{ readOnly, results: [{ speaker, conceptId, field, text, statusCode }, ...], count, ... }`. `statusCode` indicates per-concept success/failure — failures populate the code but do **not** abort the batch. `jobId` is always `null` (synchronous).

The output text is **not** written to annotations — it's returned only.

Does not mutate annotations. Acquires per-speaker lock files under `.parse-locks/` for the duration of the call.

## Example Successful Call
ORTH + IPA over `uncertain`-tagged concepts on two speakers:
```json
{
  "speakers": ["Khan01", "Khan02"],
  "tagLabels": ["uncertain"],
  "match": "any",
  "field": "both",
  "pad": 0.2
}
```

IPA only across all speakers, ALL-match:
```json
{
  "speakers": "all",
  "tagLabels": ["high_priority", "needs_review"],
  "match": "all",
  "field": "ipa"
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Ambiguous tag label                    | `409` error                                                          | Resolve via `list_concepts_by_tag` first; rename the ambiguous tag or use canonical IDs.              |
| `match: "all"` with unknown / ambiguous label | `400` error                                                  | Verify all labels via `list_concepts_by_tag` (run with `match: "all"` and the same labels first).     |
| Per-concept failure                    | One `results[i].statusCode != ok` but batch continues                | Inspect the failing entry — typically a missing concept window or audio access issue.                 |
| Lock conflict                          | `.parse-locks/<speaker>.lock` held by another job                    | Wait for the conflicting job to release, or `jobs_list_active` to find it.                            |
| Empty matched set                      | `results: []`                                                        | The tag query returned nothing — preview with `list_concepts_by_tag` first to fix the query.          |

## Agent Reasoning Notes
The synchronous-no-jobId design is intentional: this tool is a focused per-window rerun for inspection, not a long-running pipeline job. Each per-concept rerun is independent (failures don't abort the batch) so the response can mix success and error rows. The lock acquisition is real — the tool holds per-speaker locks for the duration, so it competes with other compute jobs for the same speaker. Always pair with `list_concepts_by_tag` for preview-then-run discipline; the matching semantics are identical between the two tools.

## Related Skills
- `list_concepts_by_tag` — required pre-flight preview.
- `pipeline_run`, `run_full_annotation_pipeline` (Advanced bucket) — full pipeline alternatives for persisting tier output.
- `enrichments_read`, `read_text_preview` — inspect the tag vocabulary (`parse-tags.json`).
