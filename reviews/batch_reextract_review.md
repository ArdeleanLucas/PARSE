# Review: `python/batch_reextract.py`

## Scope
Reviewed against:
- `python/batch_reextract.py`
- `INTERFACES.md`
- `PROJECT_PLAN.md`

Focus areas:
- decisions parsing correctness
- ffmpeg command generation safety
- dry-run vs execute behavior
- path handling / `--source-root`
- failure handling and reporting
- maintainability / missing tests

## Summary
No `[CRITICAL]` issues found, but there are several merge-blocking robustness problems in malformed-input paths. The happy path looks reasonable, and there are some good choices here (notably `subprocess.run()` with an argv list instead of `shell=True`, per-job execution, and post-run output existence/size checks). The biggest problems are that malformed JSON values can still crash the whole script, and timestamp/path validation is not strict enough.

## Findings

### [MAJOR] `source_wav` is presence-checked but not type-validated, so malformed JSON can crash the whole batch
**Lines:** 251-296, 325-333, 373-382

The parser only checks whether `source_wav` is `None`. If it is present but not a string (for example `{}` or `123`), the script still creates a job. That bad value later reaches `_resolve_wav_path()` / `format_cmd_for_display()` and aborts the entire run instead of warning and skipping that region.

I verified this with a minimal decisions file where `source_wav` was an object: dry-run crashed with:

```text
TypeError: sequence item 7: expected str instance, dict found
```

**Why this matters:** one malformed region should not take down the entire batch; the script already has a per-region warning/skip pattern, so this breaks the intended failure model.

**Suggested fix:**
- Require `source_wav` to be a non-empty string before building a job.
- Wrap per-region job construction in a narrow `try/except` and convert bad regions into warnings, not process-level crashes.

---

### [MAJOR] Timestamp validation accepts `NaN` / `Infinity`, producing nonsense ffmpeg commands instead of rejecting the region
**Lines:** 273-296, 359-365, 489-498

`float(start_sec)` / `float(end_sec)` accepts strings like `"nan"`, `"inf"`, and `"-inf"`. Because comparisons with `NaN` are falsey in surprising ways, the current `end_sec <= start_sec` check does not catch them.

I verified this with `start_sec: "nan"`, which produced a dry-run command like:

```text
ffmpeg -y -ss nan -t nan -i Audio_Original/Fail02/SK_Faili_F_1968.wav -c copy /tmp/out/Fail02_1_nan-338.1.wav
```

It also emitted `Fail02_1_nan-338.1.wav` as the output filename.

**Why this matters:** malformed time values should be rejected during planning, not carried into command generation.

**Suggested fix:** after coercion, reject any non-finite values via `math.isfinite()`, and also guard against negative start times if those are invalid for this workflow.

---

### [MAJOR] Optional AI metadata can crash the whole run even though it is non-essential
**Lines:** 480-484

`ai_suggestion_score` is optional metadata, but if it is present as a string (for example from a hand-edited JSON file or older export shape), this line crashes the script:

```python
score_str = f" score={score:.2f}" if score is not None else ""
```

I verified this with `"ai_suggestion_score": "0.92"`; dry-run failed with:

```text
ValueError: Unknown format code 'f' for object of type 'str'
```

**Why this matters:** auxiliary display metadata should never block extraction planning/execution.

**Suggested fix:**
- Coerce the score with `float()` inside a try/except, or
- Only format when `isinstance(score, (int, float))`, otherwise omit it with a warning.

---

### [MINOR] Falsy malformed `source_regions` values are silently ignored instead of being reported as invalid
**Lines:** 224-233

This branch:

```python
source_regions = concept_entry.get("source_regions")
if not source_regions:
    continue
if not isinstance(source_regions, dict):
    warning...
```

means `[]`, `""`, `0`, and other falsy-but-invalid values are silently treated as “nothing to do”. I verified that `"source_regions": []` exits cleanly with “No extraction jobs found” and no warning.

**Why this matters:** it hides corrupted export data and makes debugging harder.

**Suggested fix:** distinguish `None` from invalid types:

```python
if source_regions is None:
    continue
if not isinstance(source_regions, dict):
    warn...
```

---

### [MINOR] Dry-run mode does not validate source file existence, so it misses the most useful early failure case
**Lines:** 437-441, 500-517

The script only checks `Path(job.source_wav).exists()` in execute mode. In dry-run, it happily prints commands for missing inputs.

**Why this matters:** dry-run is most valuable when it catches bad `--source-root`, broken relative paths, or missing source WAVs before the user launches a long extraction run.

**Suggested fix:** perform the source existence check during planning as well, and surface a warning (or optionally a non-zero exit code when any planned job is invalid).

---

### [MINOR] Overwrite behavior is more destructive than the inline comments imply
**Lines:** 361-368, 505-509, 532-533

The code comments say “Skip if output already exists”, but the actual behavior is:
- always pass `-y` to ffmpeg
- print `STATUS : OVERWRITING existing file`
- overwrite the file unconditionally

So the behavior is internally consistent with the command, but inconsistent with the surrounding comments/variable naming (`skipped_existing`).

**Why this matters:** this is easy to misread during maintenance and makes reruns riskier than the prose suggests.

**Suggested fix:** either:
- truly skip existing outputs unless `--overwrite` is provided, or
- rename the variable/commenting to reflect actual overwrite behavior.

---

### [MINOR] `--source-root` join logic does not normalize or confine paths to the intended root
**Lines:** 325-333

`_resolve_wav_path()` simply does:

```python
Path(source_root) / wav_path
```

That allows values like `../other/location.wav` to escape the declared root. It also returns non-normalized paths such as `C:/Thesis/../other/file.wav`.

**Why this matters:** even in a trusted local workflow, `--source-root` is supposed to remap exported relative paths into a specific local corpus root. Letting relative segments escape that root weakens the safety and predictability of the option.

**Suggested fix:**
- normalize with `.resolve(strict=False)` (or Windows-safe equivalent), and
- reject paths that do not remain under `source_root` after normalization.

---

### [MINOR] Missing automated tests for the failure modes most likely to regress
There do not appear to be tests covering this script’s parsing and command-building logic.

At minimum, this file wants unit tests for:
- valid assigned region → expected ffmpeg argv
- `assigned=false` inclusion/exclusion with `--no-only-assigned`
- malformed `source_wav` types
- `NaN` / `Infinity` timestamps
- `source_regions: []` or other wrong types
- `ai_suggestion_score` as string / null / bad value
- `--source-root` remapping and `../` escape attempts
- existing output behavior (skip vs overwrite, depending on intended policy)

---

### [NIT] Small cleanup issues
- **Line 44:** `os` is imported but unused.
- **Lines 348-357:** the docstring still discusses `-to`, but the implementation uses `-t`; the prose can be tightened to match the actual command.

## Overall assessment
The core approach is sound for the expected happy path:
- decisions are flattened into jobs cleanly
- ffmpeg invocation avoids shell injection by using argv lists
- execution continues per job rather than stopping on first ffmpeg failure
- output existence/size is validated after ffmpeg returns success

But before I’d trust this on real review exports, I’d harden the parser so malformed optional fields and malformed region records degrade into warnings instead of full-process crashes, and I’d add a small focused test suite around the JSON edge cases above.
