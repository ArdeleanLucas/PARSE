# Review — `js/waveform-controller.js`

## Summary

The module has a decent skeleton: it centralizes WaveSurfer teardown, uses an `AbortController` for peaks fetches, and removes the document-level key listener on destroy. But I found several blocking issues around WaveSurfer v7 integration, stale async work, and multi-WAV correctness.

## Findings

### [CRITICAL] Plugin globals are referenced with the wrong v7 UMD names
**Lines:** 13-14, 220-223

The file says it expects global plugins at `window.WaveSurfer.RegionsPlugin` and `window.WaveSurfer.TimelinePlugin`, then calls:

```js
regionsPlugin = WaveSurfer.RegionsPlugin.create();
timelinePlugin = WaveSurfer.TimelinePlugin.create(...);
```

That does **not** match the standard WaveSurfer v7 UMD plugin exports, which expose `WaveSurfer.Regions` and `WaveSurfer.Timeline`. If the HTML shell loads the normal v7 browser builds (which is what this file’s own header implies), `RegionsPlugin` / `TimelinePlugin` will be `undefined`, and opening the panel will throw before the waveform is created.

**Why it matters:** this is a first-open runtime failure, not a cosmetic mismatch.

**Suggested fix:** use the actual v7 browser globals, or add an explicit runtime guard that fails clearly if the expected plugin objects are missing.

---

### [MAJOR] `sourceWav` selection can play one file while rendering peaks for another
**Lines:** 337-349

The controller correctly picks `wavEntry` from `sourceWav` when provided, but it always fetches peaks from the speaker-level `speakerInfo.peaks_file`:

```js
const audioUrl    = wavEntry.filename;
const durationSec = wavEntry.duration_sec;
const peaksUrl    = speakerInfo.peaks_file;
```

For speakers with multiple recordings (`source_wavs`), this means an alternate WAV can be loaded with the **primary** waveform peaks. The project plan explicitly includes multi-WAV speakers like Khan01, and the `se:panel-open` contract includes `sourceWav`, so this mismatch is not hypothetical.

**Why it matters:** region placement becomes visually misleading, and any reviewer trims based on the wrong waveform.

**Suggested fix:** make peaks/transcript metadata WAV-specific, or reject non-primary `sourceWav` values until matching peaks exist.

---

### [MAJOR] Non-mono peaks are silently mis-handled
**Lines:** 291-299

The peaks schema includes `channels`, but the controller ignores it and always passes a single channel array:

```js
const channelData = peaksData ? [peaksData.data] : undefined;
```

That only makes sense if the pipeline guarantees mono peaks forever. The broader plan/schema does not fully enforce that; it still models channel count and allows mono/stereo source files.

**Why it matters:** any stereo peaks payload will either render incorrectly or behave unpredictably, because interleaved channel data is being handed to WaveSurfer as one channel.

**Suggested fix:** either:
- explicitly validate `peaksData.channels === 1` and fail loudly, or
- split the peak data per channel before calling `load()`.

This needs a regression test with a 2-channel fixture or an explicit mono-only contract.

---

### [MAJOR] Cancellation only covers the peaks fetch; stale loads can still mutate the current instance
**Lines:** 201-312, 357-388

`AbortController` is only attached to the peaks `fetch()`. Once `createWavesurfer()` starts, the rest of the load path is not fenced by any request token, and it operates through module-global state (`wavesurfer`, `initialSeekDone`, `activeRegion`).

A bad sequence looks like this:
1. Panel A fetch completes and enters `createWavesurfer()`.
2. Panel B opens before A finishes loading.
3. B aborts the old fetch and destroys the old instance.
4. A’s pending `await wavesurfer.load(...)` / `ready` callback resolves later.
5. A’s continuation calls `seekToSec()` and touches globals that now belong to B (or are already nulled).

Because the callbacks call helpers that read the **current module-global** `wavesurfer`, stale work is not safely isolated to the instance that started it.

**Why it matters:** rapid speaker switching can produce wrong seeks, keyboard activation on the wrong panel, or other cross-talk between old and new loads.

**Suggested fix:** introduce a per-open request ID (or load token), capture a local `ws` instance inside `createWavesurfer()`, and ignore any continuation/callback whose token is no longer current.

---

### [MAJOR] Keyboard shortcuts are document-wide and not scoped to safe focus states
**Lines:** 128-165, 261-266

The handler is attached to `document` and only exempts `input`, `textarea`, and `select`:

```js
const tag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
```

While a waveform is loaded, `Space`/arrow keys will still hijack interaction on:
- focused buttons
- links
- elements with `contenteditable`
- custom widgets using ARIA roles
- any part of the page outside the source explorer panel

This is especially risky because the listener is enabled as soon as audio is ready, not when the panel or waveform itself has focus.

**Why it matters:** it can break normal UI interaction and accessibility behavior while the panel is open.

**Suggested fix:** scope shortcuts to the active panel, and ignore all interactive/contenteditable targets (not just form fields). A helper like `isInteractiveElement(target)` would make this much safer.

---

### [MINOR] Region clearing/removal is not emitted to downstream consumers
**Lines:** 92-98, 395-400, 472-475

The module emits `se:region-updated` on create/update, but when the active region is cleared or removed it only mutates local state:

```js
activeRegion.remove();
activeRegion = null;
```

There is no matching “region cleared” signal, nor a null-state `se:region-updated`. Since the public API exposes `clearActiveRegion`, downstream modules can be left displaying stale region info until the panel closes or a new region is created.

**Why it matters:** region-manager / spectrogram state can drift from actual waveform state.

**Suggested fix:** emit an explicit cleared event, or define `se:region-updated` to allow `null` bounds on clear.

---

### [MINOR] Missing guards for invalid seek/region bounds
**Lines:** 106-117, 407-414

`timeSec` and `regionDurationSec` are trusted without finite/range checks when creating regions. `seekToSec()` clamps the seek fraction, but `createRegion()` does not clamp or validate `startSec`/`endSec` against duration.

**Why it matters:** malformed event payloads can produce negative, zero-length, or off-end regions even though playback itself gets clamped.

**Suggested fix:** reject non-finite inputs, clamp bounds to `[0, duration]`, and ensure `end > start` before calling `addRegion()`.

---

### [NIT] There is dead or misleading state that makes lifecycle reasoning harder
**Lines:** 33-34, 42-43, 183, 321-322

- `currentSpeaker` is assigned, then reset in `destroyWavesurfer()`, but never read.
- `timelinePlugin` is stored but never used after creation.
- `conceptId` is destructured in `onPanelOpen()` but never used.

This is harmless by itself, but it suggests the module started moving toward stronger lifecycle/event filtering and stopped halfway.

**Suggested fix:** delete unused state or finish the intended guards (for example, speaker-aware close handling if that is needed).

## Missing tests / guards worth adding

1. **UMD smoke test:** standard v7 script tags load, `se:panel-open` creates waveform successfully.
2. **Rapid switch race:** open speaker A, immediately open speaker B, assert A cannot seek or mutate B once stale.
3. **Alternate WAV correctness:** for a multi-WAV speaker, ensure selected `sourceWav` uses matching peaks metadata.
4. **Stereo handling:** either verify stereo peaks render correctly or assert the module rejects non-mono peaks explicitly.
5. **Keyboard safety:** focused button/link/contenteditable inside and outside the panel should not trigger playback shortcuts.
6. **Region clear contract:** clearing a region updates downstream UI state, not just local `activeRegion`.

## Overall

This file is close in structure, but not ready to trust in the full Source Explorer flow yet. The plugin-global mismatch is a hard blocker, and the stale async / multi-WAV peaks problems are the next things I’d fix before integration testing.