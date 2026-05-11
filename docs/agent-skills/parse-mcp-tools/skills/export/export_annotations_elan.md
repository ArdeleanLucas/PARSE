# export_annotations_elan

**Category:** Export
**Mutability:** mutating when `outputPath` is set and `dryRun: false` (writes `.eaf` XML inside the project)
**Supports Dry Run:** Yes (`dryRun: true` or omit `outputPath`)
**Complexity:** Low
**Estimated Tokens:** ~180 (short) / ~400 (full)

## One-Sentence Summary
Exports one speaker's annotations to ELAN `.eaf` XML format for use in ELAN, EXMARaLDA, or other linguistic annotation tools.

## When to Use
- Handing off a speaker's annotation to a collaborator who works in ELAN.
- Producing per-speaker ELAN bundles for archival alongside the source audio.
- Cross-tool review (transcribers / phoneticians who prefer ELAN's tier visualization).
- Per-speaker only — there is no merged multi-speaker variant.

## When NOT to Use
- For multi-speaker merge. ELAN files are per-speaker by construction; for a merged dataset, use `export_annotations_csv` with `speaker: "all"` or the LingPy bundle.
- For phonetic-only analysis in Praat — use `export_annotations_textgrid` for the matching format.
- For LingPy / cognate analysis — use `export_lingpy_tsv` (different shape: wordlist, not interval XML).
- For full XML before previewing. The preview (no `outputPath` or `dryRun: true`) returns the first 2000 characters — enough to verify the header and tier setup before writing.

## Parameters

| Parameter  | Type    | Required | Description                                                                                              | Default | Example                              |
|------------|---------|----------|----------------------------------------------------------------------------------------------------------|---------|--------------------------------------|
| speaker    | string  | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                                                              | —       | `"Khan01"`                           |
| outputPath | string  | No       | Project-relative or absolute path inside project root (e.g. `exports/elan/Khan01.eaf`). Omit for preview. | (preview only) | `"exports/elan/Khan01.eaf"`     |
| dryRun     | boolean | No       | If `true`, preview only — never writes.                                                                  | `false` | `true`                               |

## Expected Output
Preview mode: returns `{ readOnly, preview, truncated, totalChars }`. `preview` is the first ~2000 characters of the `.eaf` XML (enough to verify the `xmin`/`xmax`/tier structure).

Write mode: writes the full `.eaf` XML inside the project and returns `{ ok: true, outputPath, totalChars }`.

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
  "outputPath": "exports/elan/Khan01.eaf",
  "dryRun": false
}
```

## Common Failure Modes & How to Recover

| Failure                                  | Symptom                                                                  | Recovery                                                                                              |
|------------------------------------------|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Missing annotation file                  | Tool error                                                               | Verify with `pipeline_state_read` that the speaker has tiers. Import via `onboard_speaker_import` if not.|
| `outputPath` outside project root        | Validation error                                                         | Use a project-relative path.                                                                          |
| ELAN opens the file but no media link    | Tier data visible but no waveform                                        | ELAN needs the corresponding WAV. Ship `audio/working/<speaker>/<speaker>.wav` alongside the `.eaf` file.|
| Existing `.eaf` silently overwritten     | Prior export at the same path replaced                                   | No auto-backup. Timestamp outputs or snapshot first.                                                  |

## Agent Reasoning Notes
ELAN is the natural format for collaborator handoff in fieldwork-driven projects — it shows tiers + audio waveform in a familiar timeline UI. For a complete handoff, bundle the `.eaf` plus the working WAV. The 2000-char preview is enough to verify ELAN-validity (header, tier list, first interval); for full validation, open the actual `.eaf` in ELAN after writing.

## Related Skills
- `export_annotations_textgrid` — same per-speaker per-format approach but for Praat.
- `export_annotations_csv` — flat dump if the collaborator can't open ELAN.
- `pipeline_state_read` (Advanced bucket) — confirm tier coverage before exporting.
