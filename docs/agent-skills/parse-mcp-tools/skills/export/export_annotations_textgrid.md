# export_annotations_textgrid

**Category:** Export
**Mutability:** mutating when `outputPath` is set and `dryRun: false` (writes `.TextGrid` inside the project)
**Supports Dry Run:** Yes (`dryRun: true` or omit `outputPath`)
**Complexity:** Low
**Estimated Tokens:** ~180 (short) / ~400 (full)

## One-Sentence Summary
Exports one speaker's annotations to Praat TextGrid format for use in Praat or other phonetic analysis tools that consume TextGrid files.

## When to Use
- Handing off a speaker to a Praat user (phoneticians, acoustic-analysis collaborators).
- Producing TextGrid bundles for archival alongside the source audio.
- When measurement workflows (formants, pitch, intensity) need PARSE's intervals as anchors in Praat.

## When NOT to Use
- For multi-speaker merge. TextGrid files are per-speaker; for a merged dump use `export_annotations_csv` with `speaker: "all"`.
- For ELAN users — use `export_annotations_elan` for the `.eaf` format.
- For LingPy / NEXUS — use `export_lingpy_tsv` / `export_nexus`.
- For full TextGrid before previewing. The preview returns the first 2000 characters — enough to verify the `xmin`/`xmax`/tier header before writing.

## Parameters

| Parameter  | Type    | Required | Description                                                                                              | Default | Example                              |
|------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| speaker    | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                              | —       | `"Khan01"`                           |
| outputPath | string  | No       | Project-relative or absolute path inside project root (e.g. `exports/textgrid/Khan01.TextGrid`). Omit for preview. | (preview only) | `"exports/textgrid/Khan01.TextGrid"` |
| dryRun     | boolean | No       | If `true`, preview only — never writes.                                                                  | `false` | `true`                               |

## Expected Output
Preview mode: returns `{ readOnly, preview, truncated, totalChars }`. `preview` is the first ~2000 characters of the `.TextGrid` (enough to verify the `xmin`/`xmax`/tier structure).

Write mode: writes the full TextGrid inside the project and returns `{ ok: true, outputPath, totalChars }`.

## Example Successful Call
Preview:
```json
{
  "speaker": "Khan01",
  "dryRun": true
}
```

Live write:
```json
{
  "speaker": "Khan01",
  "outputPath": "exports/textgrid/Khan01.TextGrid",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                                  | Recovery                                                                                              |
|------------------------------------------|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Missing annotation file                  | Tool error                                                               | Verify with `pipeline_state_read`. Import via `onboard_speaker_import` if absent.                     |
| `outputPath` outside project root        | Validation error                                                         | Use a project-relative path.                                                                          |
| Praat opens the file but no media link   | Tiers visible but no associated audio                                    | Praat reads TextGrids next to their WAV. Ship `audio/working/<speaker>/<speaker>.wav` alongside.      |
| Existing `.TextGrid` silently overwritten | Prior export at the same path replaced                                  | No auto-backup. Timestamp outputs or snapshot first.                                                  |

## Agent Reasoning Notes
TextGrid is the standard format for acoustic-measurement workflows. The PARSE-generated grid carries the same interval data as ELAN export — choose based on which tool the downstream user prefers. Like ELAN, the TextGrid alone isn't useful — pair it with the working WAV when sharing.

## Related Skills
- `export_annotations_elan` — same per-speaker shape for ELAN users.
- `export_annotations_csv` — flat dump for non-Praat / non-ELAN tooling.
- `pipeline_state_read` (Advanced bucket) — confirm tier coverage before exporting.
