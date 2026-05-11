# pipeline_state_batch

**Category:** Advanced
**Mutability:** read_only
**Supports Dry Run:** N/A (read-only preflight)
**Complexity:** Medium
**Estimated Tokens:** ~280 (short) / ~600 (full)

## One-Sentence Summary
Preflights pipeline state across multiple speakers in one call, returning per-step `done`/`can_run`/`full_coverage` rows plus top-level counts of blocked and partial-coverage speakers — the "can I kick off a batch and walk away?" check.

## When to Use
- Before starting a batch of `pipeline_run` / `run_full_annotation_pipeline` jobs across many speakers, to find which speakers are blocked or have partial coverage.
- For project-wide audit of annotation completeness — `blockedSpeakers` and `partialCoverageSpeakers` give an at-a-glance health number.
- To answer "which speakers still need STT? ORTH? IPA?" without iterating `pipeline_state_read` manually.

## When NOT to Use
- For a single known speaker — `pipeline_state_read` is leaner and returns the same shape for one row.
- To actually *start* anything — this tool is read-only. After identifying eligible speakers, hand each off to `pipeline_run`.
- For ground-truth file audit — `full_coverage` is computed from interval/segment coverage of the working WAV, not from re-reading every annotation. For artifact-level audit, read `annotations/<speaker>.parse.json` directly.

## Parameters

| Parameter | Type     | Required | Description                                                                              | Default              | Example                       |
|-----------|----------|----------|------------------------------------------------------------------------------------------|----------------------|-------------------------------|
| speakers  | string[] | No       | Restrict the preflight to this subset. Each entry is a speaker ID from `speakers_list`.  | (every annotated speaker) | `["Khan01", "Khan02"]`    |

## Expected Output
Returns `{ rows, count, blockedSpeakers, partialCoverageSpeakers, mode, previewOnly }`. Each `rows` entry carries `speaker`, `duration_sec`, and per-step objects (`normalize`, `stt`, `ortho`, `ipa`) containing:

- `done` — boolean: tier has ≥1 non-empty interval. **Not the same as "fully processed".**
- `can_run` — boolean: are preconditions met to start this step now?
- `reason` — string when `can_run` is false (e.g. `"No ortho intervals yet — run ORTH first"`).
- `intervals` / `segments` — count.
- `full_coverage` — boolean: does the tier cover the *entire* working WAV? **This is the actual "is the step finished?" signal.**
- `coverage_fraction` — float 0–1.

Top-level counters:

- `blockedSpeakers` — speakers where any step has `can_run: false`.
- `partialCoverageSpeakers` — speakers where any STT/ORTH/IPA step has `full_coverage: false`.

Does not mutate project state.

## Example Successful Call
```json
{
  "speakers": ["Khan01", "Khan02"]
}
```

Representative response:
```json
{
  "readOnly": true,
  "previewOnly": true,
  "count": 2,
  "blockedSpeakers": 1,
  "partialCoverageSpeakers": 1,
  "rows": [
    {
      "speaker": "Khan01",
      "duration_sec": 300.0,
      "stt":   {"done": true,  "can_run": true,  "segments": 82, "full_coverage": true,  "coverage_fraction": 0.99},
      "ortho": {"done": true,  "can_run": true,  "intervals": 82, "full_coverage": true, "coverage_fraction": 0.99},
      "ipa":   {"done": false, "can_run": true,  "intervals": 0,  "full_coverage": false, "coverage_fraction": 0.0}
    },
    {
      "speaker": "Khan02",
      "duration_sec": 420.0,
      "ipa": {"done": false, "can_run": false, "reason": "No ortho intervals yet — run ORTH first",
              "intervals": 0, "full_coverage": false, "coverage_fraction": 0.0}
    }
  ]
}
```

## Common Failure Modes & How to Recover

| Failure                                            | Symptom                                                              | Recovery                                                                                                            |
|----------------------------------------------------|----------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| Treating `done: true` as "step finished"           | Speaker has 30s of intervals covering a 6min recording, but `done: true` | Always gate decisions on `full_coverage` instead. The catalog description and the field's purpose are explicit: `done` only means ≥1 non-empty interval. |
| Empty `speakers` list                              | All `rows` blank or `count: 0`                                       | Omit the `speakers` arg entirely to preflight every speaker, or call `speakers_list` first to discover valid IDs.   |
| Unknown speaker ID in `speakers`                   | Row missing or error                                                 | Verify IDs against `speakers_list`. The tool may silently drop unknown entries.                                     |
| Large project, slow response                       | Long latency on full-project preflight                               | Pass a `speakers` subset to scope down. The full check reads coverage from every annotation file.                   |

## Agent Reasoning Notes
This is the orchestration tool for batch annotation work. The mental model: `done` answers "has anyone touched this tier?", `full_coverage` answers "is this tier ready to ship?". Always reason on `full_coverage` when deciding whether to skip or re-run a step. `blockedSpeakers` is the right gate for "should I attempt the batch?" — if it's nonzero, fix prerequisites first (typically by running an earlier step) rather than firing off jobs that will skip or error. Pair with `pipeline_state_read` to drill into one speaker's state in detail, and `speakers_list` to enumerate IDs.

## Related Skills
- `pipeline_state_read` — same shape, single speaker.
- `pipeline_run`, `run_full_annotation_pipeline` — the tools you'll call next, once preflight is clean.
- `speakers_list` — enumerate valid speaker IDs.
