// @vitest-environment node
import { describe, it, expect } from "vitest";
import {
  applyColor,
  computeSpectrogram,
  makeWindow,
  preEmphasize,
  type SpectrogramParams,
} from "../spectrogram-worker";

const DEFAULTS: SpectrogramParams = {
  windowLengthSec: 0.005,
  windowShape: "gaussian",
  maxFrequencyHz: 5500,
  dynamicRangeDb: 50,
  preEmphasisHz: 50,
  colorScheme: "praat",
};

describe("makeWindow", () => {
  it("Gaussian peaks at 1.0 at the center and decays at the edges", () => {
    const w = makeWindow(513, "gaussian");
    expect(w[(513 - 1) / 2]).toBeCloseTo(1.0, 6);
    expect(w[0]).toBeLessThan(0.06);
    expect(w[w.length - 1]).toBeLessThan(0.06);
    expect(w[0]).toBeGreaterThan(0);
  });

  it("Hann is zero at edges and 1 at center", () => {
    const w = makeWindow(257, "hann");
    expect(w[0]).toBeCloseTo(0, 8);
    expect(w[w.length - 1]).toBeCloseTo(0, 8);
    expect(w[(257 - 1) / 2]).toBeCloseTo(1, 6);
  });

  it("Hamming is 0.08 at edges and 1 at center", () => {
    const w = makeWindow(257, "hamming");
    expect(w[0]).toBeCloseTo(0.08, 6);
    expect(w[w.length - 1]).toBeCloseTo(0.08, 6);
    expect(w[(257 - 1) / 2]).toBeCloseTo(1, 6);
  });
});

describe("preEmphasize", () => {
  it("uses α = exp(-2π·cutoff/SR) and applies y[n] = x[n] − α·x[n-1]", () => {
    const sr = 44100;
    const cutoff = 50;
    const alpha = Math.exp((-2 * Math.PI * cutoff) / sr);
    expect(alpha).toBeCloseTo(0.99287, 4);

    const x = new Float32Array([1, 2, 3, 4]);
    const y = preEmphasize(x, sr, cutoff);
    expect(y[0]).toBeCloseTo(1, 6);
    expect(y[1]).toBeCloseTo(2 - alpha * 1, 6);
    expect(y[2]).toBeCloseTo(3 - alpha * 2, 6);
    expect(y[3]).toBeCloseTo(4 - alpha * 3, 6);
  });

  it("returns the input unchanged when cutoff <= 0", () => {
    const x = new Float32Array([0.5, -0.5, 0.5]);
    const y = preEmphasize(x, 44100, 0);
    expect(y).toBe(x);
  });
});

describe("applyColor", () => {
  it("Praat scheme: loud (1.0) → black, quiet (0.0) → white", () => {
    expect(applyColor(1.0, "praat")).toEqual([0, 0, 0]);
    expect(applyColor(0.0, "praat")).toEqual([255, 255, 255]);
  });

  it("Inverted scheme: loud (1.0) → white, quiet (0.0) → black", () => {
    expect(applyColor(1.0, "inverted")).toEqual([255, 255, 255]);
    expect(applyColor(0.0, "inverted")).toEqual([0, 0, 0]);
  });

  it("Viridis scheme returns 5-stop palette endpoints at 0 and 1", () => {
    expect(applyColor(0.0, "viridis")).toEqual([68, 1, 84]);
    expect(applyColor(1.0, "viridis")).toEqual([253, 231, 37]);
  });

  it("Clamps inputs outside [0,1]", () => {
    expect(applyColor(-1, "praat")).toEqual([255, 255, 255]);
    expect(applyColor(2, "praat")).toEqual([0, 0, 0]);
  });
});

describe("computeSpectrogram", () => {
  function makeSineSamples(freqHz: number, sampleRate: number, durationSec: number): Float32Array {
    const n = Math.floor(durationSec * sampleRate);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = Math.sin((2 * Math.PI * freqHz * i) / sampleRate);
    return out;
  }

  it("returns RGBA buffer of the expected shape with Praat defaults", () => {
    const sr = 22050;
    const audio = makeSineSamples(440, sr, 0.5);
    const result = computeSpectrogram(audio, sr, DEFAULTS);
    expect(result.rgba).toBeInstanceOf(Uint8ClampedArray);
    expect(result.rgba.length).toBe(result.width * result.height * 4);
    expect(result.width).toBeGreaterThan(0);
    expect(result.height).toBeGreaterThan(0);
  });

  it("dB-cutoff dynamic range mapping: a 440 Hz sine concentrates energy near its bin", () => {
    const sr = 22050;
    const audio = makeSineSamples(440, sr, 0.4);
    const params: SpectrogramParams = { ...DEFAULTS, preEmphasisHz: 0, colorScheme: "inverted" };
    const { rgba, width, height } = computeSpectrogram(audio, sr, params);

    const sampleColumn = Math.floor(width / 2);
    const colValues: number[] = [];
    for (let row = 0; row < height; row++) {
      colValues.push(rgba[(row * width + sampleColumn) * 4]);
    }
    const peakValue = Math.max(...colValues);
    expect(peakValue).toBeGreaterThan(200);

    const peakIdxFromTop = colValues.indexOf(peakValue);
    const peakBinFromBottom = height - 1 - peakIdxFromTop;
    const fftSize = 1 << Math.ceil(Math.log2(Math.round(0.005 * sr)));
    const expectedBin = Math.round((440 * fftSize) / sr);
    expect(Math.abs(peakBinFromBottom - expectedBin)).toBeLessThanOrEqual(2);
  });

  it("applies pre-emphasis when preEmphasisHz > 0", () => {
    const sr = 22050;
    const audio = makeSineSamples(440, sr, 0.2);
    const noEmphasis = computeSpectrogram(audio, sr, { ...DEFAULTS, preEmphasisHz: 0 });
    const withEmphasis = computeSpectrogram(audio, sr, { ...DEFAULTS, preEmphasisHz: 50 });
    expect(noEmphasis.rgba.length).toBe(withEmphasis.rgba.length);
    let diff = 0;
    for (let i = 0; i < noEmphasis.rgba.length; i++) {
      diff += Math.abs(noEmphasis.rgba[i] - withEmphasis.rgba[i]);
    }
    expect(diff).toBeGreaterThan(0);
  });
});
