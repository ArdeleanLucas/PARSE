# Review: `python/generate_peaks.py`

## Scope
Reviewed `python/generate_peaks.py` against the Source Explorer plan and interface contract, with focus on WAV parsing, peaks schema correctness, mono/stereo behavior, chunked processing, numerical edge cases, and maintainability/testing.

## Pass 1 — High-level assessment
Overall structure is clean: validation, peak generation, JSON writing, and CLI handling are separated sensibly, and the chunk loop keeps window state across chunk boundaries correctly. Mono handling, final partial-window flush, and basic large-file chunking all look conceptually sound.

The main concern is that the file currently mixes **two different peak-data formats**: it labels the output as **PeaksData v2 / audiowaveform-style JSON**, but the actual `data` payload is emitted as normalized floats. That is the biggest correctness risk in the file.

## Pass 2 — Detailed findings

### [MAJOR] The emitted JSON does not actually match the claimed PeaksData v2 schema
**Lines:** 20-29, 181-183, 202-203, 221-222, 241-248

The docstring and output object claim this is **version 2 PeaksData JSON** with `bits: 16`, but the code writes normalized float values in `[-1.0, 1.0]`.

That is not the audiowaveform/PeaksData v2 JSON format: in v2 JSON, `data` contains **integer min/max values** whose range matches `bits` (e.g. `-32768..32767` for `bits: 16`), and `length` is the number of min/max pairs per channel.

Why this matters:
- Any downstream code that expects actual v2 JSON can mis-scale the waveform badly or reject the file outright.
- The current file is effectively advertising one format while serializing another.
- This is especially risky because the plan/interface name this as a standard peaks file, so future maintainers will assume spec compatibility.

Suggested fix:
- Either **emit true 16-bit integer min/max values** and keep the v2 wrapper, or
- **Switch to a clearly custom float-peaks format** (and rename/document it as such) if the JS consumer intentionally expects normalized floats.

### [MAJOR] There is no guard against overwriting the input WAV with the output JSON
**Lines:** 312-337

The CLI accepts arbitrary input and output paths, but there is no check that `output_json` is different from `input_wav` after path normalization.

If a caller accidentally passes the same path (or two paths resolving to the same file), the script will:
1. open the WAV,
2. read and close it,
3. then overwrite that same file with JSON.

For this workflow, that means destructive loss of the source recording.

Suggested fix:
- Resolve both paths up front (`abspath`, `realpath`, or `os.path.samefile` where available) and abort if they point to the same file.
- Consider also rejecting output paths that do not end in `.json`.

### [MINOR] Input chunking is good, but memory use still grows linearly with recording length
**Lines:** 155, 202-203, 221-222, 239-257

The code correctly avoids loading the raw WAV into memory, but it still accumulates **all peak values** in a Python list before writing JSON.

For the target workflow (very long recordings), this can become much larger in RAM than the final compact JSON suggests, because Python float objects are expensive. So the implementation is "chunked" for input audio, but not truly bounded-memory end-to-end.

Why this matters:
- Large source recordings plus smaller `--samples-per-pixel` values can push memory much higher than expected.
- The current docstring implies stronger memory safety than the implementation actually provides.

Suggested fix:
- If strict memory bounds matter, stream JSON output incrementally, or buffer into a more compact numeric container before serialization.
- At minimum, document the approximate in-memory peak-list cost so operators know the real ceiling.

## Pass 3 — Edge cases, hardening, and tests

### [MINOR] The file lacks regression coverage for the numerically tricky cases
**Lines:** file-wide

This script has several edge cases that are easy to get subtly wrong, but there is no visible automated coverage for them:
- full-scale normalization (`-32768` vs `32767`)
- final partial-window flush
- stereo downmix behavior (including asymmetric / opposite-polarity channels)
- schema serialization (`length`, `channels`, `bits`, `data` shape)
- validation paths (unsupported bit depth, unsupported channels, empty WAV, bad `samples-per-pixel`)
- destructive-path guard (`input == output`)

Suggested fix:
- Add small fixture-based tests with synthetic mono/stereo WAVs.
- Refactor helper functions to raise exceptions instead of calling `sys.exit()` internally where practical; that will make failure paths much easier to unit-test.

### [NIT] The default `samples_per_pixel` is hard-coded for 44.1 kHz rather than derived from the actual file sample rate
**Lines:** 49, 295-299, 321-323

The plan says peak density should be roughly `sample_rate / 100`, but the implementation hard-codes `441`. That is fine for 44.1 kHz files, but 48 kHz input will silently produce a denser waveform than intended.

This is not a correctness break because `sample_rate` and `samples_per_pixel` are both written to the output, but it does make default resolution vary by recording.

Suggested fix:
- Compute the default after opening the WAV (e.g. around 100 peak pairs/sec based on the actual sample rate), while still allowing manual override.

## What looks good
- Validation covers the important basic constraints: existence, sample width, channel count, non-empty file, and positive sample rate.
- The chunk loop preserves min/max state across chunk boundaries correctly.
- Mono/stereo handling is simple and predictable.
- The final partial-window flush is correct and avoids dropping tail audio.
- Normalizing with `32768.0` plus clamping avoids out-of-range values from signed 16-bit PCM.

## Bottom line
The chunked WAV parsing logic is mostly solid, but I would not treat this as ready until the **peaks schema mismatch** is resolved and the **input/output overwrite guard** is added. Those are the two merge-blocking issues. The memory-growth and testability gaps are real, but secondary.