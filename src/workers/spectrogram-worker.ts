/**
 * spectrogram-worker.ts — Web Worker for STFT-based spectrogram computation
 *
 * TypeScript port of js/shared/spectrogram-worker.js.  All DSP logic is
 * identical; this file adds explicit types for the message protocol and all
 * internal functions so the rest of the React codebase can import the types
 * without importing the worker itself.
 *
 * DSP Pipeline:
 *   1. Receive Float32Array of mono PCM audio + analysis parameters
 *   2. Pre-compute a Hann window of length `windowSize`
 *   3. Step through audio in hops of (windowSize / 4) — 75% overlap
 *   4. For each frame: apply Hann window, zero-pad to next power-of-2, run FFT
 *   5. Compute magnitude spectrum (positive frequencies, DC to Nyquist)
 *   6. Convert magnitudes to decibel scale (20 * log10)
 *   7. Clip to frequency range 0–8000 Hz (or Nyquist if lower)
 *   8. Across all frames: find global dB min/max, normalise to 0–255 grayscale
 *   9. Write pixel rows: low frequency at bottom, high at top (row 0 = highest bin)
 *  10. Post result back to main thread as Uint8ClampedArray (transferred)
 *
 * Protocol (INTERFACES.md §Spectrogram Worker):
 *   In:  { type: "compute", audioData: Float32Array, sampleRate: number,
 *           windowSize: 256 | 2048, startSec: number, endSec: number }
 *   Out: { type: "result", imageData: Uint8ClampedArray, width: number,
 *           height: number, startSec: number, endSec: number }
 *   Err: { type: "error", message: string }
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
declare const self: Worker;

const MAX_COMPUTE_DURATION_SEC = 30;
const MAX_FREQ_HZ = 8000;

// ─── Message Protocol Types ───────────────────────────────────────────────────

export interface SpectrogramComputeMessage {
  type: 'compute';
  audioData: Float32Array;
  sampleRate: number;
  windowSize: 256 | 2048;
  startSec: number;
  endSec: number;
}

export interface SpectrogramResultMessage {
  type: 'result';
  imageData: Uint8ClampedArray;
  width: number;
  height: number;
  startSec: number;
  endSec: number;
}

export interface SpectrogramErrorMessage {
  type: 'error';
  message: string;
}

export type SpectrogramOutMessage = SpectrogramResultMessage | SpectrogramErrorMessage;

// ─── FFT (Cooley-Tukey radix-2, iterative in-place) ──────────────────────────

/**
 * Compute the Discrete Fourier Transform of a complex signal in-place.
 * Accepts arrays whose length is a power of 2.
 *
 * @param re — real parts (length N, must be power-of-2)
 * @param im — imaginary parts (same length)
 */
function fft(re: Float64Array, im: Float64Array): void {
  const N = re.length;

  // Bit-reversal permutation — reorders samples so butterfly stages work correctly.
  let j = 0;
  for (let i = 1; i < N; i++) {
    let bit = N >> 1;
    while (j & bit) {
      j ^= bit;
      bit >>= 1;
    }
    j ^= bit;
    if (i < j) {
      let tmp = re[i]; re[i] = re[j]; re[j] = tmp;
      tmp = im[i]; im[i] = im[j]; im[j] = tmp;
    }
  }

  for (let len = 2; len <= N; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wRe = Math.cos(ang);
    const wIm = Math.sin(ang);

    for (let i = 0; i < N; i += len) {
      let curRe = 1.0;
      let curIm = 0.0;

      for (let k = 0; k < len / 2; k++) {
        const uRe = re[i + k];
        const uIm = im[i + k];
        const vRe = re[i + k + len / 2] * curRe - im[i + k + len / 2] * curIm;
        const vIm = re[i + k + len / 2] * curIm + im[i + k + len / 2] * curRe;

        re[i + k]           = uRe + vRe;
        im[i + k]           = uIm + vIm;
        re[i + k + len / 2] = uRe - vRe;
        im[i + k + len / 2] = uIm - vIm;

        const nextRe = curRe * wRe - curIm * wIm;
        curIm        = curRe * wIm + curIm * wRe;
        curRe        = nextRe;
      }
    }
  }
}

/** Returns the next power of 2 >= n.  FFT requires power-of-2 array lengths. */
function nextPow2(n: number): number {
  if (n <= 1) return 1;
  let p = 1;
  while (p < n) p <<= 1;
  return p;
}

// ─── Hann Window ─────────────────────────────────────────────────────────────

/**
 * Generate a Hann window of length N.
 * w[n] = 0.5 * (1 − cos(2π·n / (N−1)))
 */
function hannWindow(N: number): Float64Array {
  const w = new Float64Array(N);
  for (let n = 0; n < N; n++) {
    w[n] = 0.5 * (1.0 - Math.cos((2 * Math.PI * n) / (N - 1)));
  }
  return w;
}

// ─── STFT ────────────────────────────────────────────────────────────────────

interface STFTResult {
  magnitudesDB: Float32Array[];
  numBins: number;
  numFrames: number;
}

/**
 * Short-Time Fourier Transform of a mono audio signal.
 *
 * @param samples    — mono PCM, values in [-1, 1]
 * @param sampleRate — e.g. 44100
 * @param windowSize — analysis window length (256 or 2048)
 * @param maxFreqHz  — upper frequency limit (typically 8000)
 */
function computeSTFT(
  samples: Float32Array,
  sampleRate: number,
  windowSize: number,
  maxFreqHz: number,
): STFTResult {
  const hopSize  = Math.floor(windowSize / 4);
  const fftSize  = nextPow2(windowSize);
  const hann     = hannWindow(windowSize);

  const totalBins   = Math.floor(fftSize / 2) + 1;
  const nyquist     = sampleRate / 2;
  const freqCeiling = Math.min(maxFreqHz, nyquist);
  const maxBin      = Math.min(totalBins - 1, Math.floor((freqCeiling * fftSize) / sampleRate));
  const numBins     = maxBin + 1;

  const numFrames = Math.max(1, Math.ceil((samples.length - windowSize) / hopSize) + 1);

  const re = new Float64Array(fftSize);
  const im = new Float64Array(fftSize);
  const magnitudesDB: Float32Array[] = new Array(numFrames);

  for (let frameIdx = 0; frameIdx < numFrames; frameIdx++) {
    const startSample = frameIdx * hopSize;

    for (let i = 0; i < fftSize; i++) {
      if (i < windowSize) {
        const sampleIdx = startSample + i;
        re[i] = (sampleIdx < samples.length ? samples[sampleIdx] : 0.0) * hann[i];
      } else {
        re[i] = 0.0;
      }
      im[i] = 0.0;
    }

    fft(re, im);

    const dbFrame = new Float32Array(numBins);
    const FLOOR   = 1e-10;
    for (let bin = 0; bin < numBins; bin++) {
      const mag    = Math.sqrt(re[bin] * re[bin] + im[bin] * im[bin]);
      dbFrame[bin] = 20.0 * Math.log10(Math.max(mag, FLOOR));
    }
    magnitudesDB[frameIdx] = dbFrame;
  }

  return { magnitudesDB, numBins, numFrames };
}

// ─── Message Handler ─────────────────────────────────────────────────────────

self.addEventListener('message', (evt: MessageEvent<SpectrogramComputeMessage>) => {
  const msg = evt.data;
  if (!msg || msg.type !== 'compute') return;

  try {
    const { audioData, sampleRate, windowSize, startSec, endSec } = msg;

    if (!(audioData instanceof Float32Array))
      throw new Error('audioData must be a Float32Array');
    if (!Number.isFinite(sampleRate) || sampleRate <= 0)
      throw new Error('sampleRate must be a positive finite number');
    if (windowSize !== 256 && windowSize !== 2048)
      throw new Error('windowSize must be 256 or 2048');
    if (audioData.length === 0)
      throw new Error('audioData is empty');
    if (!Number.isFinite(startSec) || !Number.isFinite(endSec))
      throw new Error('startSec and endSec must be finite numbers');
    if (startSec < 0 || endSec < 0)
      throw new Error('startSec and endSec must be >= 0');
    if (endSec <= startSec)
      throw new Error('endSec must be > startSec');

    const requestedDurationSec = endSec - startSec;
    if (requestedDurationSec > MAX_COMPUTE_DURATION_SEC)
      throw new Error('STFT request exceeds hard 30 s cap');

    const maxSamples = Math.ceil(sampleRate * MAX_COMPUTE_DURATION_SEC);
    if (audioData.length > maxSamples)
      throw new Error('audioData exceeds hard 30 s cap');

    const representedDurationSec  = audioData.length / sampleRate;
    const durationToleranceSec    = Math.max(1 / sampleRate, 0.01);
    if (Math.abs(representedDurationSec - requestedDurationSec) > durationToleranceSec)
      throw new Error('audioData length does not match requested duration');

    const { magnitudesDB, numBins, numFrames } = computeSTFT(
      audioData,
      sampleRate,
      windowSize,
      MAX_FREQ_HZ,
    );

    // Global normalisation
    let dbMin =  Infinity;
    let dbMax = -Infinity;
    for (let f = 0; f < numFrames; f++) {
      const frame = magnitudesDB[f];
      for (let b = 0; b < numBins; b++) {
        const v = frame[b];
        if (v < dbMin) dbMin = v;
        if (v > dbMax) dbMax = v;
      }
    }
    const safeRange = (dbMax - dbMin) > 0 ? dbMax - dbMin : 1.0;

    const width     = numFrames;
    const height    = numBins;
    const imageData = new Uint8ClampedArray(width * height);

    for (let frameIdx = 0; frameIdx < numFrames; frameIdx++) {
      const frame = magnitudesDB[frameIdx];
      for (let bin = 0; bin < numBins; bin++) {
        const normalised     = (frame[bin] - dbMin) / safeRange;
        const gray           = Math.round(normalised * 255);
        const row            = (numBins - 1) - bin; // low freq at bottom → high row index
        imageData[row * width + frameIdx] = gray;
      }
    }

    const out: SpectrogramOutMessage = { type: 'result', imageData, width, height, startSec, endSec };
    self.postMessage(out, [imageData.buffer]);

  } catch (err: unknown) {
    const out: SpectrogramOutMessage = {
      type: 'error',
      message: err instanceof Error ? err.message : String(err),
    };
    self.postMessage(out);
  }
});
