# pipeline_state_read

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only preflight)
**Complexity:** Low
**Estimated Tokens:** ~260 (short) / ~560 (full)

## One-Sentence Summary
Preflights pipeline state for a single speaker, returning per-step `{done, can_run, reason, coverage_*, full_coverage}` plus `duration_sec` — so the agent knows what is safe to run, what is partially done, and what is fully covered before kicking off a pipeline job.

## When to Use
- Immediately before any `pipeline_run` or `run_full_annotation_pipeline` call to confirm which steps `can_run` and which would skip.
- After a pipeline job completes, to verify the speaker reached `full_coverage: true` for all expected tiers — a `complete` status doesn't guarantee full coverage.
- When diagnosing why an agent's previous attempt didn't produce annotations — the `reason` string explains what's missing (e.g. "No ortho intervals yet").

## When NOT to Use
- For batch checks across many speakers — `pipeline_state_batch` runs the same logic across the whole project (or a `speakers` subset) and adds top-level `blockedSpeakers` / `partialCoverageSpeakers` counts.
- For artifact-level audit — `full_coverage` is computed from the annotation file's interval coverage; for direct file inspection, read `annotations/<speaker>.parse.json`.
- To actually *start* anything — this is read-only. Follow up with `pipeline_run` once preflight is clean.

## Parameters

| Parameter | Type   | Required | Description                                                       | Default | Example     |
|-----------|--------|----------|-------------------------------------------------------------------|---------|-------------|
| speaker   | string | Yes      | Speaker ID. `minLength=1`, `maxLength=200`.                       | —       | `"Khan01"`  |

## Expected Output
Returns `{ speaker, duration_sec, normalize, stt, ortho, ipa, mode, previewOnly }`. Each step object carries:

- `done` — boolean: ≥1 non-empty interval present. **Not the same as "fully processed".**
- `can_run` — boolean: are preconditions met to start this step now?
- `reason` — string when `can_run: false` (e.g. `"No source audio at audio/working/<speaker>/<speaker>.wav"`).
- `intervals` / `segments` — count.
- `coverage_start_sec`, `coverage_end_sec` — span covered by existing tier data.
- `coverage_fraction` — float 0–1.
- `full_coverage` — boolean: does the tier cover the *entire* working WAV?

**Critical distinction:** A tier with 128 intervals covering only the first 30 seconds of a 6-minute recording is still `done: true` but `full_coverage: false`. Gate re-run decisions on `full_coverage`, never on `done` alone.

Does not mutate project state.

## Example Successful Call
```json
{
  "speaker": "Khan01"
}
```

Representative response:
```json
{
  "readOnly": true,
  "speaker": "Khan01",
  "duration_sec": 300.0,
  "normalize": {"done": true, "can_run": true, "path": "audio/working/Khan01/Khan01.wav"},
  "stt":   {"done": true,  "can_run": true,  "segments": 82, "coverage_start_sec": 0.0, "coverage_end_sec": 299.2, "coverage_fraction": 0.997, "full_coverage": true},
  "ortho": {"done": true,  "can_run": true,  "intervals": 82, "coverage_start_sec": 0.0, "coverage_end_sec": 30.0,  "coverage_fraction": 0.10,  "full_coverage": false},
  "ipa":   {"done": false, "can_run": true,  "intervals": 0,  "coverage_start_sec": null, "coverage_end_sec": null, "coverage_fraction": 0.0,  "full_coverage": false}
}
```

## Common Failure Modes & How to Recover

| Failure                                              | Symptom                                                  | Recovery                                                                                                          |
|------------------------------------------------------|----------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| Misreading `done: true` as "step finished"           | Re-run skipped because tier looks populated, but only first N seconds are covered | Read `full_coverage`. Re-run with `pipeline_run` + `overwrites: {<step>: true}` to replace partial output.        |
| `can_run: false` with `reason` set                   | Step won't start                                         | Read the `reason` string verbatim and act on it — most commonly run an earlier step first (normalize → STT → ortho → IPA). |
| Unknown speaker ID                                   | Tool error                                               | Verify against `speakers_list` or `project_context_read` before retrying.                                         |
| `normalize.done: false` but you have a source WAV    | Pipeline can't find the working WAV at the expected path | The source may not have been imported through the normalize path. Run `audio_normalize_start` (Annotation bucket), or re-import via `onboard_speaker_import`. |

## Agent Reasoning Notes
This is the right tool when you have one speaker in mind and want to know exactly what's safe to run next. The full_coverage vs done distinction is the single most important thing to internalize about PARSE's pipeline state: legacy "done" semantics from the UI mean "user saw output", not "everything was processed". Use this preflight before *every* `pipeline_run` call — without it you'll fight skip-on-populated semantics blind, and may declare success on a partially-processed tier. For project-wide planning use `pipeline_state_batch` instead.

## Related Skills
- `pipeline_state_batch` — same shape across multiple speakers.
- `pipeline_run`, `run_full_annotation_pipeline` — the tools to call once preflight is clean.
- `speakers_list`, `project_context_read` — to validate speaker IDs.
