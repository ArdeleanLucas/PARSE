# prepare_compare_mode

**Category:** Comparison
**Mutability:** read_only (workflow that bundles other read-only tools)
**Supports Dry Run:** Yes (`dryRun: true`)
**Complexity:** Medium–High
**Estimated Tokens:** ~270 (short) / ~580 (full)

## One-Sentence Summary
Prepares a compare-mode bundle for a concept range across multiple speakers: loads annotations, computes a fresh cognate preview, and derives cross-speaker match previews from inline segments built from the selected concept windows — all in one structured response.

## When to Use
- Entering compare-mode for a range of concepts (e.g. concepts 1–25 across speakers Khan01..Khan04).
- After re-importing or re-annotating a speaker — pull a fresh compare bundle to see how it now lines up against the rest of the corpus.
- For batch comparative review where you want a single response containing everything the compare-mode UI needs: annotations + cognate preview + cross-speaker matches.
- Before borrowing adjudication — the compare bundle surfaces candidate cognate / borrowing pairs in one shot.

## When NOT to Use
- For one-off cognate preview without annotation loading or cross-speaker matches — use `cognate_compute_preview` directly.
- For one-off cross-speaker match preview without cognate similarity — use `cross_speaker_match_preview` directly.
- For very large concept ranges across many speakers. The workflow loads annotations for every (concept, speaker) pair in scope — bound the range and speaker list aggressively to keep response size manageable.
- To start anything mutating. This bundle is read-only; persisting decisions is a separate step (`enrichments_write`, UI compare-mode).

## Parameters

| Parameter     | Type           | Required | Description                                                                                              | Default | Example                          |
|---------------|----------------|----------|----------------------------------------------------------------------------------------------------------|---------|----------------------------------|
| concept_range | string or string[] | Yes  | Range string (`"1-25"`), single ID (`"42"`), or explicit concept ID list (`["1","2","3"]`).               | —       | `"1-25"`                         |
| speakers      | string[]       | Yes      | Speaker IDs to include in the bundle.                                                                    | —       | `["Khan01", "Khan02", "Khan03"]` |
| dryRun        | boolean        | No       | Preview the resolved speaker + concept scope without computing the full compare bundle.                  | `false` | `true`                           |

## Expected Output
On `dryRun: true`: returns the resolved concept ID list and speaker list (so the caller can confirm the scope) without computing the cognate/match previews.

On `dryRun: false`: returns the full compare bundle: `{ readOnly, conceptIds, speakers, annotations: {...}, cognatePreview: {...}, crossSpeakerMatches: {...}, ... }`.

Does not mutate project state.

## Example Successful Call
Dry run (confirm scope):
```json
{
  "concept_range": "1-25",
  "speakers": ["Khan01", "Khan02", "Khan03"],
  "dryRun": true
}
```

Full bundle:
```json
{
  "concept_range": ["1", "2", "3", "4", "5"],
  "speakers": ["Khan01", "Khan02"]
}
```

Single concept across all speakers in scope:
```json
{
  "concept_range": "42",
  "speakers": ["Khan01", "Khan02", "Khan03", "Khan04"]
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Empty scope after resolution           | `dryRun` shows no concepts / speakers                                | Verify the range string vs `project_context_read` and verify speaker IDs against `speakers_list`.    |
| Range string ambiguous                 | Concepts unexpectedly missing or included                            | Prefer explicit ID lists for production calls; `"1-25"` is convenient but ID gaps in the project can surprise. |
| Response too large                     | Token / payload limit exceeded                                       | Narrow the range or speakers. The workflow wraps several read tools, so the response grows multiplicatively. |
| Cognate preview misaligned             | Cognate groups in the bundle look wrong                              | Tune `cognate_compute_preview` parameters in a separate call (this workflow uses defaults); for full control over threshold etc., compose the underlying tools manually. |

## Agent Reasoning Notes
This is the one-shot workflow for "give me the compare-mode view of these concepts across these speakers". It composes `cognate_compute_preview` and `cross_speaker_match_preview` with annotation loading. When you need per-tool tuning (custom thresholds, `topK`, etc.), call the underlying tools directly instead. Always run `dryRun: true` first on large scopes to confirm the resolved (concepts, speakers) sets — the workflow doesn't bound size on its own, and an over-broad scope can produce responses the agent can't comfortably consume.

## Related Skills
- `cognate_compute_preview` — the underlying cognate preview, callable directly for parameter tuning.
- `cross_speaker_match_preview` — the underlying cross-speaker match preview.
- `annotation_read` — the annotation-load primitive this workflow wraps.
- `project_context_read`, `speakers_list` — validate concept range and speaker IDs.
