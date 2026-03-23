# `js/spectrogram-worker.js` review

## Summary

I reviewed `js/spectrogram-worker.js` against `INTERFACES.md` and the spectrogram sections of `PROJECT_PLAN.md`.

Overall, the core FFT/STFT path is readable and largely sound: the radix-2 FFT looks correct, the worker uses a transferable result buffer, and the image orientation matches the plan (low frequencies at the bottom, high at the top).

I found **1 blocking issue**, **3 non-blocking issues**, and **1 nit**.

---

## Findings

### [MAJOR] The worker does not enforce the plan’s hard `<=30s` compute cap

**Where:** `spectrogram-worker.js:214-245`

`PROJECT_PLAN.md` explicitly calls out a **hard cap of <=30s** as the mitigation for client-side spectrogram cost. This worker currently trusts the caller completely: it validates `audioData`, `sampleRate`, and `windowSize`, but it does **not** reject oversized jobs.

That means a wrapper bug, future refactor, or alternate caller can still send a much larger buffer and reintroduce the exact freeze / memory-risk the plan is trying to prevent. The current implementation keeps the full dB matrix in memory before normalization, so cost scales linearly with input duration.

For example, a 10-minute 44.1 kHz clip would push `magnitudesDB` into roughly **150 MB+** territory before JS array overhead, plus the output image buffer and FFT working buffers.

**Why this matters:** the project plan treats the cap as a safety boundary, not just a UI preference.

**Suggested fix:** fail fast before STFT when either of these is false:

- `Number.isFinite(startSec)` / `Number.isFinite(endSec)`
- `endSec > startSec`
- `endSec - startSec <= 30`
- `audioData.length <= Math.ceil(sampleRate * 30)` (optionally with a small tolerance for rounding)

If the cap is exceeded, return the normal worker error payload.

---

### [MINOR] Frequency clipping uses `Math.ceil`, so the output can include bins above the documented 8 kHz ceiling

**Where:** `spectrogram-worker.js:150-156`

The file comments say the spectrum is clipped to `0–8000 Hz` (or Nyquist if lower), but the code computes:

```js
const maxBin = Math.min(
  totalBins - 1,
  Math.ceil(freqCeiling * fftSize / sampleRate)
);
```

Using `Math.ceil` includes the **first bin above** `freqCeiling` whenever `8000 Hz` does not land exactly on a bin boundary. For example:

- `44.1 kHz, windowSize=2048` -> top included bin is ~`8011 Hz`
- `44.1 kHz, windowSize=256` -> top included bin is ~`8096 Hz`

That is only a one-bin overshoot, so this is not catastrophic, but it does contradict the documented contract.

**Suggested fix:** use `Math.floor(...)` if the intent is “never exceed 8 kHz”.

---

### [MINOR] `startSec` / `endSec` are echoed back without validation

**Where:** `spectrogram-worker.js:215-221`, `297-305`

The worker passes `startSec` and `endSec` straight through to the result message, but it never checks that they are finite, ordered, or consistent with the submitted audio buffer.

So these invalid inputs currently succeed and produce misleading metadata:

- `startSec = NaN`
- `endSec <= startSec`
- negative timestamps
- timestamps that do not match `audioData.length / sampleRate`

**Why this matters:** even if the FFT finishes, the UI can end up rendering a valid image with invalid timing metadata, which makes alignment bugs and stale-result bugs much harder to diagnose.

**Suggested fix:** validate both timestamps and, ideally, sanity-check them against the audio duration represented by `audioData.length / sampleRate`.

---

### [MINOR] The worker keeps more intermediate data in memory than a display-only pipeline needs

**Where:** `spectrogram-worker.js:166-171`, `191-200`, `247-292`

The implementation stores one `Float64Array` per frame in `magnitudesDB`, then makes a full second pass to find global min/max, then a third pass to write grayscale pixels.

This is understandable and simple, but it is heavier than necessary:

- `Float64Array` doubles memory vs `Float32Array`
- `Array<Float64Array>` adds object overhead
- the design requires retaining the whole spectrogram in memory before writing the image

Under the intended `<=30s` cap this is probably acceptable, but it reduces headroom and makes accidental oversize requests much more expensive.

**Suggested fix:**

- store dB frames as `Float32Array`
- track `dbMin` / `dbMax` during STFT generation instead of in a later pass
- if this gets hot, consider a single contiguous buffer instead of an array of per-frame typed arrays

---

### [NIT] The frame-count comment does not match the implemented framing rule

**Where:** `spectrogram-worker.js:161-164`

The comment says:

> A frame is valid as long as its start index `< samples.length`

But the actual formula:

```js
Math.max(1, Math.ceil((samples.length - windowSize) / hopSize) + 1)
```

is really “enough left-aligned windows to cover the tail with zero-padding”, not “every possible start before the end of the buffer”.

The implementation itself is reasonable; the comment is just more absolute than the code.

**Suggested fix:** rewrite the comment so future maintainers do not derive the wrong time-axis assumptions from it.

---

## Positive notes

- The FFT butterfly implementation looks correct for the intended radix-2 sizes.
- The vertical image flip is consistent with the documented orientation: low frequency at the bottom, high frequency at the top.
- Returning `imageData` with a transferred buffer is the right performance choice for the worker boundary.
- Input validation for `audioData`, `sampleRate`, and allowed `windowSize` values is a good start.
