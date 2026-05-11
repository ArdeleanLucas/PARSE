# project_context_read

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~210 (short) / ~460 (full)

## One-Sentence Summary
Reads high-level PARSE project context — project metadata, source-index summary, annotation inventory, enrichment summary, AI config, and constraints — the canonical "what's in this project?" probe.

## When to Use
- At the start of almost any chat session — establish situational awareness (speakers, concepts, project name, status) before deciding what to do.
- Validating speaker / concept IDs before passing them to mutating tools.
- Inspecting AI config (which provider, which model is set on the project).
- Capturing project state as audit evidence in PR / handoff documentation.
- As a scope check before broad operations (`pipeline_state_batch`, bulk exports, etc.).

## When NOT to Use
- For detailed annotation-interval data — that's `annotation_read` (Annotation bucket).
- For per-tier coverage / can_run analysis — that's `pipeline_state_read` / `pipeline_state_batch` (Advanced bucket).
- For cognate / enrichment data — that's `enrichments_read`.
- For chat-memory recall — that's `parse_memory_read`.
- For full annotation dumps. The `annotation_inventory` block is a summary (counts, names, status), not interval data.

## Parameters

| Parameter   | Type     | Required | Description                                                                                              | Default              | Example                                  |
|-------------|----------|----------|----------------------------------------------------------------------------------------------------------|----------------------|------------------------------------------|
| include     | string[] | No       | Subset of context blocks. Valid: `project`, `source_index`, `annotation_inventory`, `enrichments_summary`, `ai_config`, `constraints`. | (all) | `["project", "annotation_inventory"]` |
| maxSpeakers | integer  | No       | Cap on per-speaker rows in inventory blocks. `minimum=1`, `maximum=500`.                                  | (server default)     | `100`                                    |

## Expected Output
Returns `{ readOnly, project?, source_index?, annotation_inventory?, enrichments_summary?, ai_config?, constraints? }` — each requested block is present; unrequested ones are omitted.

- `project` — name, root path, language, configured tiers.
- `source_index` — speakers with registered sources, primary WAV per speaker.
- `annotation_inventory` — per-speaker counts (concepts, intervals, tier coverage summary).
- `enrichments_summary` — counts of cognate sets, borrowing flags, lexeme notes.
- `ai_config` — active provider, model, exposure mode.
- `constraints` — project-level policy constraints exposed by the catalog.

Does not mutate project state.

## Example Successful Call
Default (all blocks):
```json
{}
```

Scoped to project + inventory:
```json
{
  "include": ["project", "annotation_inventory"],
  "maxSpeakers": 100
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                              | Recovery                                                                                              |
|------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Truncated inventory                      | Speaker rows in `annotation_inventory` cut off                       | Increase `maxSpeakers` (up to 500), or scope by speaker via `pipeline_state_batch` with explicit list.|
| Missing `enrichments_summary`            | Block absent or empty                                                 | `parse-enrichments.json` may not exist yet. Use `enrichments_read` directly to confirm.               |
| Wrong AI config visible                  | `ai_config` shows unexpected provider/model                          | Verify `~/.parse/config.yaml` or env vars. The tool reflects active config, not desired config.       |

## Agent Reasoning Notes
This is the cheapest "where am I, what do I have?" probe. Most session-loop agents should call it first thing — it's read-only, bounded, and answers most "is this valid?" questions without per-tool drilling. For deeper inspection, pivot to bucket-specific tools (`pipeline_state_*` for compute readiness, `annotation_read` for interval data, `enrichments_read` for cognate state). The `include` filter is worth using on every call — most tasks only need 1–2 blocks, and the response shrinks significantly.

## Related Skills
- `speakers_list` — narrower alternative when you only need the speaker enumeration.
- `pipeline_state_batch`, `pipeline_state_read` (Advanced bucket) — per-tier coverage detail.
- `annotation_read` (Annotation bucket) — interval-level data for one speaker.
- `enrichments_read` — full cognate / borrowing / similarity data.
- `parse_memory_read` — persistent chat memory (separate from project state).
- `mcp_get_exposure_mode` — adapter configuration (separate from project config).
