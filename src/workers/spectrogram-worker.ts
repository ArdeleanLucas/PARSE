/**
 * Praat-style STFT spectrogram worker.
 *
 * DSP pipeline (matches Praat defaults):
 *   1. Apply pre-emphasis filter (1st-order IIR, default cutoff 50 Hz, 6 dB/oct shelf)
 *   2. Step through audio with hop = max(1, round(windowLen / 8))
 *   3. Window each frame with Gaussian (or Hann/Hamming) shape
 *   4. Zero-pad to next power-of-2 and run radix-2 FFT
 *   5. Magnitude → dB (20 log10)
 *   6. Map dB to [0,1] with cutoff: gray = clamp((dB - (max - dynamicRange)) / dynamicRange)
 *   7. Apply color scheme (Praat: dark = loud on white) and emit RGBA
 */

declare const self: Worker;

export type WindowShape = "gaussian" | "hann" | "hamming";
export type ColorScheme = "praat" | "inverted" | "viridis";

export interface SpectrogramParams {
  windowLengthSec: number;
  windowShape: WindowShape;
  maxFrequencyHz: number;
  dynamicRangeDb: number;
  preEmphasisHz: number;
  colorScheme: ColorScheme;
}

export interface SpectrogramComputeMessage {
  type: "compute";
  audioData: Float32Array;
  sampleRate: number;
  params: SpectrogramParams;
}

export interface SpectrogramResultMessage {
  type: "result";
  rgba: Uint8ClampedArray;
  width: number;
  height: number;
}

export interface SpectrogramErrorMessage {
  type: "error";
  message: string;
}

export type SpectrogramOutMessage = SpectrogramResultMessage | SpectrogramErrorMessage;

const HARD_CAP_SEC = 30;

function fft(re: Float64Array, im: Float64Array): void {
  const N = re.length;
  let j = 0;
  for (let i = 1; i < N; i++) {
    let bit = N >> 1;
    while (j & bit) {
      j ^= bit;
      bit >>= 1;
    }
    j ^= bit;
    if (i < j) {
      let t = re[i];
      re[i] = re[j];
      re[j] = t;
      t = im[i];
      im[i] = im[j];
      im[j] = t;
    }
  }
  for (let len = 2; len <= N; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wRe = Math.cos(ang);
    const wIm = Math.sin(ang);
    for (let i = 0; i < N; i += len) {
      let curRe = 1;
      let curIm = 0;
      const half = len >> 1;
      for (let k = 0; k < half; k++) {
        const uRe = re[i + k];
        const uIm = im[i + k];
        const vRe = re[i + k + half] * curRe - im[i + k + half] * curIm;
        const vIm = re[i + k + half] * curIm + im[i + k + half] * curRe;
        re[i + k] = uRe + vRe;
        im[i + k] = uIm + vIm;
        re[i + k + half] = uRe - vRe;
        im[i + k + half] = uIm - vIm;
        const nextRe = curRe * wRe - curIm * wIm;
        curIm = curRe * wIm + curIm * wRe;
        curRe = nextRe;
      }
    }
  }
}

function nextPow2(n: number): number {
  let p = 1;
  while (p < n) p <<= 1;
  return p;
}

export function makeWindow(N: number, shape: WindowShape): Float64Array {
  const w = new Float64Array(N);
  if (shape === "hann") {
    for (let n = 0; n < N; n++) w[n] = 0.5 * (1 - Math.cos((2 * Math.PI * n) / (N - 1)));
  } else if (shape === "hamming") {
    for (let n = 0; n < N; n++) w[n] = 0.54 - 0.46 * Math.cos((2 * Math.PI * n) / (N - 1));
  } else {
    const center = (N - 1) / 2;
    const denom = (N - 1) * (N - 1);
    for (let n = 0; n < N; n++) {
      const d = n - center;
      w[n] = Math.exp((-12 * d * d) / denom);
    }
  }
  return w;
}

export function preEmphasize(samples: Float32Array, sampleRate: number, cutoffHz: number): Float32Array {
  if (cutoffHz <= 0) return samples;
  const alpha = Math.exp((-2 * Math.PI * cutoffHz) / sampleRate);
  const out = new Float32Array(samples.length);
  out[0] = samples[0];
  for (let i = 1; i < samples.length; i++) out[i] = samples[i] - alpha * samples[i - 1];
  return out;
}

const VIRIDIS: Array<[number, number, number]> = [
  [68, 1, 84],
  [59, 82, 139],
  [33, 145, 140],
  [94, 201, 98],
  [253, 231, 37],
];

export function applyColor(value: number, scheme: ColorScheme): [number, number, number] {
  const v = Math.max(0, Math.min(1, value));
  if (scheme === "praat") {
    const g = Math.round((1 - v) * 255);
    return [g, g, g];
  }
  if (scheme === "inverted") {
    const g = Math.round(v * 255);
    return [g, g, g];
  }
  const t = v * (VIRIDIS.length - 1);
  const i = Math.floor(t);
  const f = t - i;
  const a = VIRIDIS[i];
  const b = VIRIDIS[Math.min(VIRIDIS.length - 1, i + 1)];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

export function computeSpectrogram(
  audio: Float32Array,
  sampleRate: number,
  params: SpectrogramParams,
): { rgba: Uint8ClampedArray; width: number; height: number } {
  const winLen = Math.max(8, Math.round(params.windowLengthSec * sampleRate));
  const fftSize = nextPow2(winLen);
  const hop = Math.max(1, Math.round(winLen / 8));
  const win = makeWindow(winLen, params.windowShape);

  const nyquist = sampleRate / 2;
  const fCeil = Math.min(params.maxFrequencyHz, nyquist);
  const totalBins = (fftSize >> 1) + 1;
  const numBins = Math.min(totalBins, Math.max(1, Math.floor((fCeil * fftSize) / sampleRate) + 1));

  const emphasized = preEmphasize(audio, sampleRate, params.preEmphasisHz);
  const numFrames = Math.max(1, Math.floor((emphasized.length - winLen) / hop) + 1);

  const re = new Float64Array(fftSize);
  const im = new Float64Array(fftSize);
  const dbFrames: Float32Array[] = new Array(numFrames);
  let dbMax = -Infinity;

  for (let f = 0; f < numFrames; f++) {
    const start = f * hop;
    for (let i = 0; i < fftSize; i++) {
      if (i < winLen) {
        const idx = start + i;
        re[i] = idx < emphasized.length ? emphasized[idx] * win[i] : 0;
      } else {
        re[i] = 0;
      }
      im[i] = 0;
    }
    fft(re, im);
    const frame = new Float32Array(numBins);
    for (let b = 0; b < numBins; b++) {
      const mag = Math.sqrt(re[b] * re[b] + im[b] * im[b]);
      const db = 20 * Math.log10(Math.max(mag, 1e-10));
      frame[b] = db;
      if (db > dbMax) dbMax = db;
    }
    dbFrames[f] = frame;
  }

  const dbFloor = dbMax - params.dynamicRangeDb;
  const range = params.dynamicRangeDb > 0 ? params.dynamicRangeDb : 1;
  const width = numFrames;
  const height = numBins;
  const rgba = new Uint8ClampedArray(width * height * 4);

  for (let f = 0; f < numFrames; f++) {
    const frame = dbFrames[f];
    for (let b = 0; b < numBins; b++) {
      const norm = Math.max(0, Math.min(1, (frame[b] - dbFloor) / range));
      const row = numBins - 1 - b;
      const idx = (row * width + f) * 4;
      const [r, g, bl] = applyColor(norm, params.colorScheme);
      rgba[idx] = r;
      rgba[idx + 1] = g;
      rgba[idx + 2] = bl;
      rgba[idx + 3] = 255;
    }
  }

  return { rgba, width, height };
}

// Module-load guard: register the worker listener only when running inside a
// Worker context. Lets the same module be imported in node-environment tests.
if (typeof self !== "undefined" && typeof (self as Worker).addEventListener === "function") {
  (self as Worker).addEventListener("message", (evt: MessageEvent<SpectrogramComputeMessage>) => {
    const msg = evt.data;
    if (!msg || msg.type !== "compute") return;
    try {
      const { audioData, sampleRate, params } = msg;
      if (!(audioData instanceof Float32Array)) throw new Error("audioData must be Float32Array");
      if (audioData.length === 0) throw new Error("audioData empty");
      if (audioData.length / sampleRate > HARD_CAP_SEC) throw new Error(`exceeds ${HARD_CAP_SEC}s cap`);
      if (params.windowLengthSec <= 0) throw new Error("windowLengthSec must be > 0");
      if (params.dynamicRangeDb <= 0) throw new Error("dynamicRangeDb must be > 0");

      const { rgba, width, height } = computeSpectrogram(audioData, sampleRate, params);
      const out: SpectrogramOutMessage = { type: "result", rgba, width, height };
      (self as Worker).postMessage(out, [rgba.buffer]);
    } catch (err) {
      const out: SpectrogramOutMessage = {
        type: "error",
        message: err instanceof Error ? err.message : String(err),
      };
      (self as Worker).postMessage(out);
    }
  });
}
