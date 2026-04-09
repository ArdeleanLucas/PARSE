/**
 * useSpectrogram.ts — React hook for Worker-backed STFT spectrogram rendering
 *
 * Usage
 * -----
 *   const canvasRef = useRef<HTMLCanvasElement | null>(null);
 *
 *   // audioReady flips true inside useWaveSurfer's onReady callback
 *   useSpectrogram({ enabled: spectroOn && audioReady, wsRef, canvasRef });
 *
 * Lifecycle
 * ---------
 *   When `enabled` becomes true:
 *     1. Read decoded AudioBuffer from wsRef.current.getDecodedData()
 *     2. Mix down to mono (if stereo)
 *     3. Spin up spectrogram-worker.ts (Vite module worker)
 *     4. Post { type:'compute', audioData, sampleRate, windowSize, startSec:0, endSec:duration }
 *        — audioData buffer is transferred to avoid a copy
 *     5. On 'result': expand grayscale bytes to RGBA, paint offscreen canvas,
 *        scale-draw onto the display canvas
 *     6. On 'error': emit console.warn, leave canvas as-is
 *
 *   When `enabled` becomes false:
 *     — Clear the canvas
 *     — Terminate the worker (if any)
 *
 *   On unmount:
 *     — Terminate any live worker
 */

import WaveSurfer from 'wavesurfer.js';
import { useEffect, useRef } from 'react';
import type { SpectrogramOutMessage } from '../workers/spectrogram-worker';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface UseSpectrogramOptions {
  /** Set true when the spectrogram button is on AND audio is decoded. */
  enabled: boolean;
  /** Ref to the live WaveSurfer instance, returned by useWaveSurfer. */
  wsRef: React.RefObject<WaveSurfer | null>;
  /** Ref to the <canvas> element that will receive the rendered spectrogram. */
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  /** FFT window length.  2048 → finer frequency resolution; 256 → faster.
   *  Default: 2048 (recommended for phonetics work). */
  windowSize?: 256 | 2048;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSpectrogram({
  enabled,
  wsRef,
  canvasRef,
  windowSize = 2048,
}: UseSpectrogramOptions): void {
  const workerRef = useRef<Worker | null>(null);

  // ── Terminate worker on unmount ───────────────────────────────────────────
  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
    };
  }, []);

  // ── Main effect: compute when enabled flips on ────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;

    if (!enabled) {
      // Tear down any running worker and clear the canvas.
      workerRef.current?.terminate();
      workerRef.current = null;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    if (!canvas) return;

    const ws = wsRef.current;
    if (!ws) return;

    const audioBuffer = ws.getDecodedData();
    if (!audioBuffer) {
      // Caller should only set enabled=true after onReady; this is a safety guard.
      console.warn('[useSpectrogram] getDecodedData() returned null — skipping');
      return;
    }

    // ── Mix down to mono ───────────────────────────────────────────────────
    const numChannels = audioBuffer.numberOfChannels;
    const length      = audioBuffer.length;
    const sampleRate  = audioBuffer.sampleRate;
    const duration    = audioBuffer.duration;

    let monoData: Float32Array;
    if (numChannels === 1) {
      // Slice so we can safely transfer the buffer without detaching the AudioBuffer.
      monoData = audioBuffer.getChannelData(0).slice();
    } else {
      monoData = new Float32Array(length);
      for (let ch = 0; ch < numChannels; ch++) {
        const channelData = audioBuffer.getChannelData(ch);
        for (let i = 0; i < length; i++) {
          monoData[i] += channelData[i];
        }
      }
      const invChannels = 1 / numChannels;
      for (let i = 0; i < length; i++) {
        monoData[i] *= invChannels;
      }
    }

    // ── Spin up the worker ─────────────────────────────────────────────────
    workerRef.current?.terminate();
    const worker = new Worker(
      new URL('../workers/spectrogram-worker.ts', import.meta.url),
      { type: 'module' },
    );
    workerRef.current = worker;

    worker.onmessage = (evt: MessageEvent<SpectrogramOutMessage>) => {
      const msg = evt.data;

      if (msg.type === 'error') {
        console.warn('[useSpectrogram] Worker error:', msg.message);
        return;
      }

      if (msg.type === 'result') {
        const { imageData, width, height } = msg;
        const cnv = canvasRef.current;
        if (!cnv) return;

        // Expand grayscale byte array → RGBA for ImageData
        const rgba = new Uint8ClampedArray(width * height * 4);
        for (let i = 0; i < width * height; i++) {
          const g          = imageData[i];
          rgba[i * 4]      = g;   // R
          rgba[i * 4 + 1]  = g;   // G
          rgba[i * 4 + 2]  = g;   // B
          rgba[i * 4 + 3]  = 255; // A
        }

        // Paint to an offscreen canvas at native resolution, then scale to display
        const offscreen    = document.createElement('canvas');
        offscreen.width    = width;
        offscreen.height   = height;
        const offCtx       = offscreen.getContext('2d');
        if (!offCtx) return;
        offCtx.putImageData(new ImageData(rgba, width, height), 0, 0);

        const displayCtx = cnv.getContext('2d');
        if (!displayCtx) return;
        displayCtx.clearRect(0, 0, cnv.width, cnv.height);
        displayCtx.drawImage(offscreen, 0, 0, cnv.width, cnv.height);
      }
    };

    worker.onerror = (err) => {
      console.warn('[useSpectrogram] Worker load error:', err.message);
    };

    // Transfer monoData buffer to avoid a copy (~zero-cost for large files)
    worker.postMessage(
      {
        type: 'compute',
        audioData: monoData,
        sampleRate,
        windowSize,
        startSec: 0,
        endSec:   duration,
      },
      [monoData.buffer],
    );

    return () => {
      worker.terminate();
      workerRef.current = null;
    };
    // wsRef and canvasRef are stable React refs — they don't change identity.
    // enabled encodes both spectroOn AND audioReady, so it's the right trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, windowSize]);
}
