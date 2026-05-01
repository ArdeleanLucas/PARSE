/**
 * useSpectrogram — drives the Praat-style STFT spectrogram worker and paints
 * the result onto a canvas. Settings come from a Zustand store; the hook only
 * needs the worker enabled flag, the live WaveSurfer ref, the canvas ref, and
 * the parameter object.
 *
 * Key fix vs. prior implementation: canvas pixel dimensions are snapped to the
 * element's bounding rect × devicePixelRatio before posting to the worker, so
 * the rendered image fills its container instead of falling back to the HTML
 * canvas default of 300×150.
 *
 * Audio slicing: the worker has a 30s hard cap (memory/perf safety). Long PARSE
 * recordings are 1-2+ hours, so the hook slices the AudioBuffer to a `timeRange`
 * before posting. Callers (AnnotateView) pass the active concept's interval
 * with a small padding so the spectrogram aligns with what's being annotated.
 * Without a `timeRange`, defaults to the first MAX_DEFAULT_DURATION_SEC of audio.
 */

import WaveSurfer from "wavesurfer.js";
import { useEffect, useRef } from "react";
import type {
  SpectrogramOutMessage,
  SpectrogramParams,
} from "../workers/spectrogram-worker";

const MAX_DEFAULT_DURATION_SEC = 30;

export interface UseSpectrogramTimeRange {
  startSec: number;
  endSec: number;
}

export interface UseSpectrogramOptions {
  enabled: boolean;
  wsRef: React.RefObject<WaveSurfer | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  params: SpectrogramParams;
  /**
   * Optional time window to render. When omitted, the hook renders the first
   * MAX_DEFAULT_DURATION_SEC of audio. PARSE recordings are typically 1–2+ h,
   * so passing the active concept's interval (with a small padding) keeps the
   * worker under its 30 s hard cap and aligns the canvas with annotation work.
   */
  timeRange?: UseSpectrogramTimeRange;
}

export function useSpectrogram({
  enabled,
  wsRef,
  canvasRef,
  params,
  timeRange,
}: UseSpectrogramOptions): void {
  const workerRef = useRef<Worker | null>(null);

  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;

    if (!enabled) {
      workerRef.current?.terminate();
      workerRef.current = null;
      if (canvas) {
        const ctx = canvas.getContext("2d");
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    if (!canvas) return;

    const ws = wsRef.current;
    if (!ws) return;

    const audioBuffer = ws.getDecodedData();
    if (!audioBuffer) {
      console.warn("[useSpectrogram] getDecodedData() returned null — skipping");
      return;
    }

    const sampleRate = audioBuffer.sampleRate;
    const totalSamples = audioBuffer.length;

    // Resolve the slice [startSample, endSample). Default = first 30 s of audio.
    let startSample = 0;
    let endSample = Math.min(totalSamples, Math.ceil(MAX_DEFAULT_DURATION_SEC * sampleRate));
    if (timeRange && Number.isFinite(timeRange.startSec) && Number.isFinite(timeRange.endSec)) {
      startSample = Math.max(0, Math.floor(timeRange.startSec * sampleRate));
      endSample = Math.min(totalSamples, Math.ceil(timeRange.endSec * sampleRate));
    }
    if (endSample <= startSample) {
      console.warn("[useSpectrogram] empty timeRange — skipping");
      return;
    }

    // Snap canvas pixel dims to its rendered size before computing — fixes the
    // prior 300×150 default that produced a barely-visible blur.
    const rect = canvas.getBoundingClientRect();
    const dpr = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));

    const numChannels = audioBuffer.numberOfChannels;
    const sliceLength = endSample - startSample;

    // Mix to mono ONLY over the slice — avoids OOM on long recordings.
    let monoData: Float32Array;
    if (numChannels === 1) {
      monoData = audioBuffer.getChannelData(0).slice(startSample, endSample);
    } else {
      monoData = new Float32Array(sliceLength);
      for (let ch = 0; ch < numChannels; ch++) {
        const channelData = audioBuffer.getChannelData(ch);
        for (let i = 0; i < sliceLength; i++) monoData[i] += channelData[startSample + i];
      }
      const inv = 1 / numChannels;
      for (let i = 0; i < sliceLength; i++) monoData[i] *= inv;
    }

    workerRef.current?.terminate();
    const worker = new Worker(
      new URL("../workers/spectrogram-worker.ts", import.meta.url),
      { type: "module" },
    );
    workerRef.current = worker;

    worker.onmessage = (evt: MessageEvent<SpectrogramOutMessage>) => {
      const msg = evt.data;
      if (msg.type === "error") {
        console.warn("[useSpectrogram] Worker error:", msg.message);
        return;
      }
      if (msg.type === "result") {
        const { rgba, width, height } = msg;
        const cnv = canvasRef.current;
        if (!cnv) return;
        const offscreen = document.createElement("canvas");
        offscreen.width = width;
        offscreen.height = height;
        const offCtx = offscreen.getContext("2d");
        if (!offCtx) return;
        // Copy into a fresh ArrayBuffer-backed array so ImageData accepts it
        // under TS's strict ArrayBuffer/SharedArrayBuffer type discrimination.
        const localRgba = new Uint8ClampedArray(rgba);
        offCtx.putImageData(new ImageData(localRgba, width, height), 0, 0);

        const displayCtx = cnv.getContext("2d");
        if (!displayCtx) return;
        displayCtx.imageSmoothingEnabled = true;
        displayCtx.imageSmoothingQuality = "high";
        displayCtx.clearRect(0, 0, cnv.width, cnv.height);
        displayCtx.drawImage(offscreen, 0, 0, cnv.width, cnv.height);
      }
    };

    worker.onerror = (err) => {
      console.warn("[useSpectrogram] Worker load error:", err.message);
    };

    worker.postMessage(
      {
        type: "compute",
        audioData: monoData,
        sampleRate,
        params,
      },
      [monoData.buffer],
    );

    return () => {
      worker.terminate();
      workerRef.current = null;
    };
  }, [
    enabled,
    params.windowLengthSec,
    params.windowShape,
    params.maxFrequencyHz,
    params.dynamicRangeDb,
    params.preEmphasisHz,
    params.colorScheme,
    timeRange?.startSec,
    timeRange?.endSec,
    canvasRef,
    wsRef,
  ]);
}
