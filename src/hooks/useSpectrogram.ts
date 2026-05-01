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
 */

import WaveSurfer from "wavesurfer.js";
import { useEffect, useRef } from "react";
import type {
  SpectrogramOutMessage,
  SpectrogramParams,
} from "../workers/spectrogram-worker";

export interface UseSpectrogramOptions {
  enabled: boolean;
  wsRef: React.RefObject<WaveSurfer | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  params: SpectrogramParams;
}

export function useSpectrogram({
  enabled,
  wsRef,
  canvasRef,
  params,
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

    const rect = canvas.getBoundingClientRect();
    const dpr = (typeof window !== "undefined" && window.devicePixelRatio) || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));

    const numChannels = audioBuffer.numberOfChannels;
    const length = audioBuffer.length;
    const sampleRate = audioBuffer.sampleRate;

    let monoData: Float32Array;
    if (numChannels === 1) {
      monoData = audioBuffer.getChannelData(0).slice();
    } else {
      monoData = new Float32Array(length);
      for (let ch = 0; ch < numChannels; ch++) {
        const channelData = audioBuffer.getChannelData(ch);
        for (let i = 0; i < length; i++) monoData[i] += channelData[i];
      }
      const inv = 1 / numChannels;
      for (let i = 0; i < length; i++) monoData[i] *= inv;
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
    canvasRef,
    wsRef,
  ]);
}
