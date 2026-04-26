import type WaveSurfer from "wavesurfer.js";

import type { PeaksJson, UseWaveSurferOptions } from "./types";

export function getChannelDataFromPeaks(peaks: PeaksJson): number[][] | undefined {
  if (peaks.data == null) return undefined;
  const channels = Number(peaks.channels);
  const data = peaks.data;
  if (!Number.isFinite(channels) || channels <= 1) return [data as number[]];
  if (Array.isArray(data) && data.length === channels && data.every((channel) => Array.isArray(channel))) {
    return data as number[][];
  }
  console.warn("[useWaveSurfer] Unsupported multi-channel peaks payload; loading without peaks.");
  return undefined;
}

export async function loadWaveSurferAudio(
  ws: WaveSurfer,
  options: UseWaveSurferOptions,
  abortCtrl: AbortController,
): Promise<void> {
  if (!options.peaksUrl) {
    ws.load(options.audioUrl);
    return;
  }
  try {
    const response = await fetch(options.peaksUrl, { signal: abortCtrl.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const peaksJson = (await response.json()) as PeaksJson;
    const channelData = getChannelDataFromPeaks(peaksJson);
    if (channelData) ws.load(options.audioUrl, channelData, options.durationSec);
    else ws.load(options.audioUrl);
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    console.warn("[useWaveSurfer] Peaks fetch failed, loading without peaks:", error);
    ws.load(options.audioUrl);
  }
}
