# Review — `python/generate_source_index.py`

## Summary

Happy-path behavior is mostly aligned with the SourceIndex contract: the script enforces exactly one primary WAV and the single-vs-multi-WAV naming rule for `peaks_file` / `transcript_file` matches the intended pattern.

The main problems are around **validation hardening** and **path normalization**. Right now the generator can either:
- crash with a raw Python traceback on malformed nested input, or
- emit a `source_index.json` that technically writes but violates the schema / runtime assumptions in `INTERFACES.md` and `PROJECT_PLAN.md`.

## Findings

### [MAJOR] Nested `wav_files` entries are not type-checked before field access, so malformed manifests can crash with a traceback instead of a controlled validation error
**Lines:** 125-130

`validate_speaker()` assumes every `wav_files` item is a dict and immediately does `wav.get(...)`. If a manifest contains `null`, a string, or any other non-object inside `wav_files`, the script raises `AttributeError` before `_fail()` can produce a useful message.

Example bad input:

```json
{
  "speakers": {
    "Fail01": {
      "wav_files": [null],
      "has_csv": true,
      "lexicon_start_sec": 506
    }
  }
}
```

This currently fails with a Python traceback, not a clean schema error.

**Why it matters:** this is exactly the kind of failure mode that makes data-prep scripts annoying to debug in practice. The function docstring promises descriptive validation failures, but nested malformed entries currently bypass that.

**Suggested fix:** before using `wav.get(...)`, explicitly validate `isinstance(wav, dict)` and fail with a message like `Speaker 'X' wav[0]: value must be an object`.

---

### [MAJOR] Required fields are presence-checked but not schema-validated, so the script can emit contract-breaking or unusable `source_index.json`
**Lines:** 121-150, 197-224

The script checks that fields exist, but it does **not** validate their types or ranges:
- `duration_sec`
- `file_size_bytes`
- `bit_depth`
- `sample_rate`
- `channels`
- `lexicon_start_sec`
- `has_csv`
- `notes`

A few concrete bad cases that currently pass through:
- `"lexicon_start_sec": null` at the WAV level
- `"duration_sec": "7200"` as a string
- negative or zero durations / file sizes
- `"has_csv": "false"` as a string
- unsupported audio metadata like `bit_depth: 24` or `channels: 6`

This is especially important because the project plan explicitly says unsupported audio formats should be caught during prep (`16-bit PCM`, mono/stereo constraints, valid seekable timestamps). Right now the script will happily encode values that later break waveform loading, seek behavior, or client assumptions.

**Why it matters:** `INTERFACES.md` defines these as strongly typed fields consumed directly by JS. Letting `null`, strings, or unsupported audio specs through pushes failures downstream into harder-to-debug browser/runtime issues.

**Suggested fix:** add explicit validators for:
- finite numeric types for durations / offsets
- positive integers for `file_size_bytes`, `sample_rate`, `channels`, `bit_depth`
- boolean type for `has_csv`
- optional string-only `notes`
- project-specific constraints such as `bit_depth == 16` and `channels in {1, 2}` if this script is meant to enforce Phase 0 output

---

### [MAJOR] `filename` is copied verbatim from the manifest, but the SourceIndex contract requires a relative URL path
**Lines:** 158-167, 180-188, 201-202

`transform_speaker()` writes:

```python
"filename": wav["path"]
```

with no normalization or validation.

But `INTERFACES.md` describes `filename` as a **relative URL path**, and `PROJECT_PLAN.md` consistently uses forward-slash relative paths like:

- `Audio_Original/Fail01/Faili_M_1984.wav`
- `Audio_Original/Khan01_missing/REC00002.wav`

If the ffprobe manifest contains Windows-style or absolute paths such as:
- `C:\Users\Lucas\Thesis\Audio_Original\Fail01\Faili_M_1984.wav`
- `Audio_Original\Fail01\Faili_M_1984.wav`

then the generated JSON will violate the contract and likely break browser fetches / URL generation. It also risks leaking machine-specific absolute paths into an artifact that is supposed to contain web-facing relative paths.

**Why it matters:** this script is the boundary where OS-native file discovery becomes browser-consumable metadata. That is the right place to normalize or reject non-URL-safe paths.

**Suggested fix:** normalize manifest paths to project-relative forward-slash form and reject absolute paths. Example output invariant:

```text
Audio_Original/Fail01/Faili_M_1984.wav
```

not backslashes, drive letters, or absolute filesystem paths.

---

### [MINOR] Validation is tightly coupled to `sys.exit()`, which makes the core logic harder to test and reuse
**Lines:** 95-98, 101-150, 233-247

All validation helpers terminate the process via `_fail()` instead of raising structured exceptions. That works for the CLI entrypoint, but it makes `build_source_index()` / `validate_speaker()` awkward to unit test and easy to misuse from other code.

**Why it matters:** this file already has cleanly separable pure-ish helpers (`validate_speaker`, `_peaks_and_transcript_paths`, `transform_speaker`, `build_source_index`). Returning/raising structured errors would make them much easier to test and reuse.

**Suggested fix:** raise `ValueError` / custom `ManifestValidationError` from helper functions, then let `main()` catch and print a single CLI-friendly error.

## Recommended test coverage

I did not find obvious companion tests for this script under `source-explorer/`. At minimum, add tests for:

1. **Single-WAV speaker path generation**
   - `peaks/Fail01.json`
   - `coarse_transcripts/Fail01.json`

2. **Multi-WAV speaker path generation**
   - primary WAV chosen by `is_primary`
   - suffixed output like `peaks/Khan01_REC00002.json`

3. **Malformed nested entries**
   - non-dict `wav_files` items
   - missing required nested fields

4. **`lexicon_start_sec` validation**
   - missing at both levels → reject
   - explicit `null` → reject
   - string value → reject

5. **Audio metadata validation**
   - negative/zero duration
   - non-integer `channels`, `sample_rate`, `bit_depth`
   - unsupported `bit_depth` / channel counts if Phase 0 invariants are enforced here

6. **Path normalization**
   - Windows backslash paths normalized or rejected
   - absolute paths rejected
   - output always uses relative forward-slash URL paths

## Bottom line

The script is structurally close, but it still needs stronger validation at the manifest boundary. The biggest risk is not the happy path — it is silently emitting bad `source_index.json` (or crashing with a traceback) when the ffprobe manifest is even slightly malformed or OS-shaped instead of URL-shaped.
