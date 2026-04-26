import { useRef } from "react";
import type WaveSurfer from "wavesurfer.js";
import type RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";

import { useWaveSurferInstance } from "./useWaveSurferInstance";
import { useWaveSurferPlayback } from "./useWaveSurferPlayback";
import { useWaveSurferRegions } from "./useWaveSurferRegions";
import type { UseWaveSurferOptions, UseWaveSurferResult, WaveSurferRefs, WsRegion } from "./types";

export function useWaveSurfer(options: UseWaveSurferOptions): UseWaveSurferResult {
  const refs: WaveSurferRefs = {
    wsRef: useRef<WaveSurfer | null>(null),
    regionsRef: useRef<RegionsPlugin | null>(null),
    activeRegionRef: useRef<WsRegion | null>(null),
    abortControllerRef: useRef<AbortController | null>(null),
    clipEndRef: useRef<number | null>(null),
    regionPrimedRef: useRef(false),
  };

  const playback = useWaveSurferPlayback(refs);
  const regions = useWaveSurferRegions(refs);
  useWaveSurferInstance(options, refs);

  return { ...playback, ...regions, wsRef: refs.wsRef, regionsRef: refs.regionsRef };
}
