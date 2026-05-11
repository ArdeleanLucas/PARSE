# speakers_list

**Category:** Project
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only)
**Complexity:** Low
**Estimated Tokens:** ~150 (short) / ~340 (full)

## One-Sentence Summary
Lists every speaker with an annotation file under `annotations/` — filters out non-annotation entries (e.g. `backups/`) so the list is directly usable as input to `pipeline_run` and other speaker-iterating tools.

## When to Use
- Starting any batch pipeline run — get the list of speakers, then pass it to `pipeline_state_batch` (Advanced bucket) for readiness check, then iterate `pipeline_run` per speaker.
- Validating a speaker ID before mutating tools (`apply_timestamp_offset`, `csv_only_reimport`, etc.).
- Capacity / progress reporting: "how many speakers are in this project?".
- As a cheap discovery probe at the start of any session.

## When NOT to Use
- For project-wide metadata beyond just speaker names — `project_context_read` returns a richer set of context blocks (project metadata, annotation inventory, enrichments summary).
- For per-speaker pipeline coverage — that's `pipeline_state_read` / `pipeline_state_batch` (Advanced bucket).
- For speakers registered in `source_index.json` but not yet annotated. This tool lists annotation files; for source-index inspection use `source_index_validate` with `mode: "full"` and an empty manifest, or read the file via `read_text_preview`.

## Parameters
No parameters. Pass `{}`.

## Expected Output
Returns `{ readOnly, speakers: [...], count }`. `speakers` is a flat list of speaker IDs derived from filenames under `annotations/`, filtered to exclude non-annotation entries.

Does not mutate project state.

## Example Successful Call
```json
{}
```

Representative response:
```json
{
  "readOnly": true,
  "speakers": ["Khan01", "Khan02", "Khan03"],
  "count": 3
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Speaker registered but not listed      | `source_index.json` has an entry but `speakers_list` doesn't include it | The speaker doesn't have an annotation file yet. Run `onboard_speaker_import` (Annotation bucket) — that creates the annotation scaffold. |
| Listed speaker has no source           | Annotation file exists but `source_index.json` has no entry          | Stale annotation file. Either re-import via `onboard_speaker_import` or remove the orphan annotation. |
| Unexpected entries                     | Backup directory names or other non-speaker entries appear           | This shouldn't happen — the tool filters them out. If it does, treat it as a project state issue and clean up `annotations/`. |

## Agent Reasoning Notes
This is the cheapest "who's in this project?" probe. The deliberate filtering of non-annotation entries (e.g. `backups/`) is what makes the output directly usable as input to `pipeline_run` — no manual list-cleanup required. Pair with `pipeline_state_batch` for the standard batch-pipeline flow: enumerate → preflight → iterate.

## Related Skills
- `project_context_read` — broader project state, including this list plus more context.
- `pipeline_state_batch`, `pipeline_state_read` (Advanced bucket) — per-tier coverage / readiness per speaker.
- `pipeline_run`, `run_full_annotation_pipeline` (Advanced bucket) — the typical consumers of this list.
- `source_index_validate` — inspect / repair `source_index.json` separately.
