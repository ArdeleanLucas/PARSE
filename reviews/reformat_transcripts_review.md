# Review — `python/reformat_transcripts.py`

## Summary

Good bones overall: the CLI is clear, UTF-8 input plus `ensure_ascii=False` preserves Kurdish text correctly, and sorting normalized segments by `start` is the right default. The main problems are around metadata inference and validation, not text handling.

**Blocking issues:** 3
**Non-blocking issues:** 3

---

## Findings

### [MAJOR] Batch mode silently overwrites multi-file speakers instead of handling them explicitly
**Where:** lines 326-327, 348-366

Batch output is always named `<Speaker>.json`, and each input file for that speaker is written to the same path:

- `out_file = output_dir / f"{inferred_speaker}.json"`
- `reformat(..., output_path=str(out_file))`

That is risky in this project because the plan explicitly lists **multiple coarse files for `Khan01`**. So batch mode currently processes all of them and silently keeps only whichever file sorts last. That means correctness depends on filename ordering, not an explicit rule like “use the primary WAV” or “merge these inputs”.

I verified this with a small synthetic batch run: the second `Khan01_*_coarse.json` simply overwrote the first without any warning.

**Why this matters:** this is silent data loss / silent policy selection in the exact corpus the tool is meant to process.

**Suggested fix:**
- fail fast when multiple files map to the same output speaker unless an explicit policy is provided;
- or encode source identity in the output filename;
- or implement the project-plan rule explicitly (e.g. manifest-driven primary selection / merge behavior).

---

### [MAJOR] `source_wav` inference does not satisfy the declared schema and can emit invalid transcript metadata
**Where:** lines 33-34, 225-245, 289-293

The docstring says that in batch mode the script will infer metadata from **filename and JSON content**, but `source_wav` is only probed from top-level JSON keys. If none are present, the script writes:

```json
"source_wav": ""
```

That does **not** match the `CoarseTranscript` contract in `INTERFACES.md`, which expects a real relative path like:

```json
"source_wav": "Audio_Original/Mand01/Mandali_M_1900_01.wav"
```

I confirmed this with a quick single-file repro: omitting `--source-wav` produces an output file with an empty string.

**Why this matters:** the output schema becomes self-inconsistent, and downstream code cannot rely on `source_wav` being meaningful.

**Suggested fix:**
- either require `--source-wav` / manifest input when it cannot be inferred safely;
- or actually implement filename-based inference for the known corpus layout;
- but do **not** silently write an empty path into the final schema.

---

### [MAJOR] Segment timestamp validation is too weak; invalid times can reach output and even produce non-standard JSON
**Where:** lines 142-151, 271-301

`normalise_segment()` converts `start`/`end` to floats, but it does not reject:

- `NaN` / `Infinity`
- negative times
- `end < start`

This matters more than it looks, because Python’s `json.dump()` allows NaN by default. So a malformed timestamp can end up serialized as:

```json
{"start": NaN}
```

which is **not valid JSON** for browser `JSON.parse()`.

Reversed or negative ranges are also invalid under the transcript schema and can break waveform/transcript synchronization.

**Suggested fix:** after float conversion, validate with something like:
- `math.isfinite(start)` and `math.isfinite(end)`
- `start >= 0`
- `end >= start`

Also consider `json.dump(..., allow_nan=False)` so bad values fail loudly instead of leaking into output.

---

### [MINOR] The “permissive input shape” handling still has brittle crash paths on malformed inputs
**Where:** lines 79-84, 87-114, 117-151

A few edge cases currently bypass the intended friendly `ValueError` flow:

1. `_first_existing()` returns the first **present** key even when the value is `None`. So `{start: null, start_sec: 12.3}` still behaves as “missing start”, even though a usable alias exists.
2. `extract_segments([])` falls through to `data.values()` and raises `AttributeError` instead of the advertised `ValueError`.
3. `normalise_segment()` assumes each raw segment is a dict; malformed list items can crash when building the error message (`raw.keys()`).

**Why this matters:** the script claims permissive input-shape handling, but malformed inputs can still produce confusing tracebacks instead of actionable diagnostics.

**Suggested fix:**
- skip aliases whose value is `None`;
- guard `extract_segments()` and `normalise_segment()` with explicit type checks;
- keep all malformed-input failures on the same clean `ValueError` path.

---

### [MINOR] `duration_sec` fallback is only transcript coverage, not the recording duration promised by the schema
**Where:** lines 172-176, 275-287

When top-level duration is missing, the script uses the maximum segment end time. But the plan/interface describe `duration_sec` as the **total recording duration** (from `ffprobe`), not just the end of the last transcript window.

For sparse coarse transcripts, those are not guaranteed to be the same thing.

**Why this matters:** consumers may treat `duration_sec` as full-file duration and make UI decisions based on it.

**Suggested fix:**
- prefer duration from a manifest / `source_index` / CLI input;
- if you keep this fallback, label it as an approximation and avoid presenting it as canonical full recording duration.

---

### [MINOR] Missing tests around the exact failure modes this script is responsible for
**Where:** whole file / design level

This file needs tests more than it needs extra heuristics. The highest-value cases are all untested right now:

- duplicate-speaker batch inputs (`Khan01_*`-style collisions)
- missing `source_wav` metadata
- filename-based speaker inference edge cases
- `None` in one alias key with valid data in another
- empty/malformed segment lists
- invalid timestamps (`NaN`, `inf`, negative, `end < start`)
- Unicode round-tripping for Kurdish text

Also, `reformat()` / `batch_reformat()` call `sys.exit()` directly, which makes unit testing harder than necessary.

**Suggested fix:** let helpers raise exceptions and keep `sys.exit()` in `main()` only, then add fixture-based tests for the cases above.

---

## Positive notes

- **Unicode/text preservation looks good.** Reading and writing with UTF-8 plus `ensure_ascii=False` is the correct choice here.
- **Sorting by `start` is sensible.** It protects downstream UI code from mildly disordered inputs.
- **Error intent is good.** The file is clearly trying to produce helpful diagnostics; it just needs stronger validation and more explicit metadata policy.
