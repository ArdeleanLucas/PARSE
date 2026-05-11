# transcript_reformat

**Category:** Annotation
**Mutability:** mutating when `outputPath` is set (writes a project artifact)
**Supports Dry Run:** Yes (`dryRun: true` returns the parsed JSON without writing)
**Complexity:** Low
**Estimated Tokens:** ~230 (short) / ~500 (full)

## One-Sentence Summary
Reformats a `*_coarse.json` alignment file into the PARSE CoarseTranscript schema (`{ speaker, source_wav, duration_sec, segments[] }`), returning the result inline or writing it inside the project if `outputPath` is supplied.

## When to Use
- Adapting legacy `*_coarse.json` files (produced by an older PARSE version or external tooling) to the current CoarseTranscript schema before importing.
- Bridging between an external alignment producer and PARSE's expected `coarse_transcripts/<speaker>.json` shape.
- For one-off conversions where you want to inspect the reformatted JSON (`dryRun: true` or omit `outputPath`) before writing.

## When NOT to Use
- For files that are already in the PARSE schema — there's nothing to do.
- To run STT. This tool reshapes existing alignment data, it does not generate it. Use `stt_start` / `stt_word_level_start` for that.
- For arbitrary JSON reformatting — the tool understands the legacy `*_coarse.json` shape specifically.

## Parameters

| Parameter   | Type    | Required | Description                                                                                  | Default              | Example                              |
|-------------|---------|----------|----------------------------------------------------------------------------------------------|----------------------|--------------------------------------|
| inputPath   | string  | Yes      | Path to the `*_coarse.json` file to reformat. `minLength=1`, `maxLength=512`.                | —                    | `"legacy/Khan01_coarse.json"`        |
| outputPath  | string  | No       | Project-relative or absolute path inside project root to write the result. Omit to return inline. `minLength=1`, `maxLength=512`. | (return inline) | `"coarse_transcripts/Khan01.json"` |
| speaker     | string  | No       | Override speaker ID (inferred from filename if omitted). `minLength=1`, `maxLength=200`.     | (inferred)           | `"Khan01"`                           |
| sourceWav   | string  | No       | Override source WAV path written into output metadata. `minLength=1`, `maxLength=512`.       | (inferred)           | `"audio/working/Khan01/Khan01.wav"` |
| durationSec | number  | No       | Override total duration (inferred from segments if omitted). `minimum=0.0`.                  | (inferred)           | `300.0`                              |
| dryRun      | boolean | No       | If `true`, return parsed JSON without writing (regardless of `outputPath`).                  | `false`              | `true`                               |

## Expected Output
On dry-run or when `outputPath` is omitted: returns the reformatted JSON object inline.

On `outputPath` + `dryRun: false`: writes the file inside the project root and returns `{ ok: true, outputPath, speaker, durationSec, segmentCount }`.

## Example Successful Call
Inline reformat (no write):
```json
{
  "inputPath": "legacy/Khan01_coarse.json"
}
```

Write to project, overriding speaker:
```json
{
  "inputPath": "legacy/Khan01_coarse.json",
  "outputPath": "coarse_transcripts/Khan01.json",
  "speaker": "Khan01",
  "sourceWav": "audio/working/Khan01/Khan01.wav"
}
```

Dry-run with explicit overrides:
```json
{
  "inputPath": "legacy/Khan01_coarse.json",
  "outputPath": "coarse_transcripts/Khan01.json",
  "speaker": "Khan01",
  "dryRun": true
}
```

## Common Failure Modes & How to Recover

| Failure                                | Symptom                                                              | Recovery                                                                                              |
|----------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| Input not in expected `*_coarse.json` shape | Tool error / partial reformat                                   | Inspect the file manually; PARSE expects a specific top-level shape with segments / words.            |
| Wrong `speaker` inferred from filename | Reformatted JSON has wrong speaker ID                                | Pass `speaker` explicitly. The override is the canonical mechanism.                                   |
| `outputPath` outside project           | Validation error                                                     | Use a project-relative path or an absolute path under the project root.                               |
| Existing output file silently overwritten | Prior `coarse_transcripts/<speaker>.json` replaced              | No auto-backup. Snapshot first if rollback may be needed.                                             |

## Agent Reasoning Notes
This is a format-bridge tool. Reach for it when an external producer (or a previous PARSE version) gave you a `*_coarse.json` and you need the active schema. After the reformat, downstream tools (`forced_align_start`, `compute_boundaries_start`, etc.) consume the standard `coarse_transcripts/<speaker>.json` shape — no further conversion needed. For the standard PARSE pipeline running on canonical sources, you'd typically never need this; it's specifically for migration and external-bridge cases.

## Related Skills
- `stt_start`, `stt_word_level_start` — produce the cache from audio (rather than reformat existing JSON).
- `read_text_preview` — inspect the input file before reformatting.
