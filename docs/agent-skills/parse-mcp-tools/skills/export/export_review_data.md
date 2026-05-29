# export_review_data

**Category:** Export
**Mutability:** mutating (writes review_tool export artifacts under the requested output directory)
**Supports Dry Run:** No
**Complexity:** Medium
**Estimated Tokens:** ~250 (short) / ~650 (full)

## One-Sentence Summary
Exports a PARSE workspace to the legacy `review_tool` v4.1 schema: `review_data.json`, timestamps, analytical fields, contact-language reference forms, and optional clipped audio.

## When to Use
- Preparing a reviewer-facing `review_tool` bundle from the current PARSE workspace.
- Verifying default-mode export coverage against a known speaker subset.
- Creating a temporary export for inspection before running `scripts/sync_review_tool.sh`.

## When NOT to Use
- For LingPy/NEXUS phylogenetic exports — use `export_complete_lingpy_dataset`, `export_lingpy_tsv`, or `export_nexus`.
- When you need a preview-only no-write call; this tool writes to `out` by design.
- When the output directory is a production `review_tool` clone and the user has not approved overwriting/staging files.

## Parameters

| Parameter | Type | Required | Description | Default | Example |
|---|---|---:|---|---|---|
| `workspace` | string | Yes | Absolute path to the PARSE workspace root. | — | `"/path/to/parse-workspace"` |
| `out` | string | Yes | Output directory for `review_data.json`, timestamps, and optional audio clips. | — | `"/tmp/review-export"` |
| `tag_id` | string | No | `parse-tags.json` tag id used to filter concepts. | `custom-sk-concept-list` | `"custom-sk-concept-list"` |
| `contact_config` | string | No | Path to `sil_contact_languages.json`; omit to use the exporter/script default. | exporter default | `"/path/to/config/sil_contact_languages.json"` |
| `speakers` | string[] | No | Speaker subset; project order is preserved and unknown speakers fail. | all project speakers | `["SpeakerA", "SpeakerB"]` |
| `skip_audio` | boolean | No | Skip ffmpeg clip materialization and write JSON/timestamps only. | `false` | `true` |

## Expected Output
Returns a summary with `review_data_path`, `concept_count`, `speaker_count`, `clip_plan_count`, `audio_clipped`, `audio_errors`, `skipped_audio`, and `analytical_coverage` counters. The output directory receives `review_data.json`, timestamp CSVs, and audio clips unless `skip_audio` is true.

## Example Successful Call
```json
{
  "workspace": "/path/to/parse-workspace",
  "out": "/tmp/parse-review-export",
  "speakers": ["SpeakerA", "SpeakerB", "SpeakerC"],
  "skip_audio": true
}
```

## Common Failure Modes & How to Recover

| Failure | Symptom | Recovery |
|---|---|---|
| Unknown speaker subset | `invalid_args` / failed execution | Re-check `speakers_list` or omit `speakers` to export all project speakers. |
| Empty contact refs | Low contact-reference counters in the summary | Confirm the workspace contact cache path or set `contact_config` explicitly. |
| Output overwrote a clone unexpectedly | Dirty `review_tool` clone | Inspect `git -C <out> diff`; reset only after preserving any needed local work. |
| Audio clipping slow or unavailable | ffmpeg errors / long runtime | Retry with `skip_audio: true` for JSON-only validation, then fix ffmpeg/audio paths before final sync. |

## Agent Reasoning Notes
Prefer a temporary `out` directory for validation. When preparing the real `review_tool` clone, report the exact output path and summary counts, then require a human push/merge decision; the wrapper intentionally does not auto-push.

## Related Skills
- `export_complete_lingpy_dataset` — research dataset export path.
- `speakers_list` — choose and verify speaker subsets.
- `contact_lexeme_lookup` — refresh contact forms before export when appropriate.
