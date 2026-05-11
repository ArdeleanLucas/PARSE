# annotation_read

**Category:** Annotation
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only inspection)
**Complexity:** Low
**Estimated Tokens:** ~190 (short) / ~430 (full)

## One-Sentence Summary
Reads one speaker's annotation JSON (`annotations/<speaker>.parse.json`) with optional concept/tier filtering and a hard cap on returned intervals — the safe inspection path that won't dump multi-megabyte files into the agent's context.

## When to Use
- Auditing what's actually in a speaker's annotation file after a pipeline job claims success — read_only ground truth, not a job summary.
- Inspecting a specific concept row's intervals across tiers (`conceptIds: ["12"]` + `includeTiers: ["ortho", "ipa"]`).
- Before any mutating tool that targets the annotation file (`apply_timestamp_offset`, `compute_boundaries_start`, `ipa_transcribe_acoustic_start`) — confirm the file looks like you expect.
- Diagnosing why a downstream step thinks a tier is empty or partial — `intervals` count and the actual interval content settle the question.

## When NOT to Use
- For a full-project annotation dump — call once per speaker, or use `speakers_list` + iterate. There is no batch read tool.
- To read the raw file directly. The tool applies project-aware loading (resolves the canonical `.parse.json` path, handles missing-file errors cleanly); shelling out via `read_text_preview` works but bypasses these safeguards.
- For pipeline-state preflight ("is STT done? how much coverage?") — use `pipeline_state_read` instead; it computes coverage fractions and `can_run` flags rather than dumping raw intervals.

## Parameters

| Parameter     | Type     | Required | Description                                                                       | Default       | Example                  |
|---------------|----------|----------|-----------------------------------------------------------------------------------|---------------|--------------------------|
| speaker       | string   | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                       | —             | `"Khan01"`               |
| conceptIds    | string[] | No       | Restrict the read to intervals belonging to these concept IDs.                    | (all)         | `["12", "13", "14"]`     |
| includeTiers  | string[] | No       | Restrict the read to specific tiers. Common tiers: `ortho`, `ipa`, `ortho_words`. | (all)         | `["ortho", "ipa"]`       |
| maxIntervals  | integer  | No       | Hard cap on returned intervals. `minimum=1`, `maximum=5000`.                      | (server default) | `200`                 |

## Expected Output
Returns the annotation JSON content limited by the filters: `{ readOnly, speaker, tiers: { <tier>: [{ id, start_sec, end_sec, text, concept_id, ... }] }, conceptCount, intervalCount, truncated }`. When `maxIntervals` is hit, `truncated: true` signals that the response is a partial view.

Does not mutate project state.

## Example Successful Call
```json
{
  "speaker": "Khan01",
  "conceptIds": ["12", "13"],
  "includeTiers": ["ortho", "ipa"],
  "maxIntervals": 100
}
```

## Common Failure Modes & How to Recover

| Failure                          | Symptom                                                | Recovery                                                                                              |
|----------------------------------|--------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Unknown speaker                  | Tool error — annotation file not found                 | Verify against `speakers_list` or `project_context_read`. Speaker may not be onboarded yet.           |
| Empty tier despite expecting data | `tiers.<x>` empty array                                | The tier hasn't been populated. Call `pipeline_state_read` to see which step is missing.              |
| Truncated response               | `truncated: true` in result                            | Either tighten `conceptIds`/`includeTiers` filters or raise `maxIntervals` (capped at 5000).          |
| Unknown concept IDs              | Filtered result empty but tier has data                | Verify IDs in `project_context_read` (`concepts` section).                                            |

## Agent Reasoning Notes
This is the right tool for "show me what's actually in the file" questions. Pair with `pipeline_state_read` for the higher-level coverage view, and with `apply_timestamp_offset` / `compute_boundaries_start` / `ipa_transcribe_acoustic_start` as a pre/post audit when those mutate the same file. Avoid using it as a project-wide audit primitive — the tool is per-speaker by design.

## Related Skills
- `pipeline_state_read` — coverage/state view; better for "is this done?" questions.
- `speakers_list` — enumerate valid speaker IDs.
- `apply_timestamp_offset`, `compute_boundaries_start`, `ipa_transcribe_acoustic_start` — mutating tools that target the same file; audit before/after.
