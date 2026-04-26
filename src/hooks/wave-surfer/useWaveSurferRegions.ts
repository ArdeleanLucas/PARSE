import { useCallback } from "react";

import type { WaveSurferRefs, WaveSurferRegionsControls, WsRegion } from "./types";
import { WAVE_SURFER_REGION_COLOR } from "./types";

export function useWaveSurferRegions(refs: WaveSurferRefs): WaveSurferRegionsControls {
  const { regionsRef, activeRegionRef, clipEndRef, regionPrimedRef } = refs;

  const clearRegions = useCallback(() => {
    activeRegionRef.current?.remove();
    activeRegionRef.current = null;
  }, [activeRegionRef]);

  const addRegion = useCallback((start: number, end: number, id?: string) => {
    clearRegions();
    if (!regionsRef.current) return;
    const region = regionsRef.current.addRegion({
      start,
      end,
      id: id ?? `r-${start}`,
      color: WAVE_SURFER_REGION_COLOR,
      drag: true,
      resize: true,
    }) as unknown as WsRegion;
    activeRegionRef.current = region;
    regionPrimedRef.current = true;
    clipEndRef.current = null;
  }, [activeRegionRef, clearRegions, clipEndRef, regionPrimedRef, regionsRef]);

  const playRegion = useCallback(() => {
    if (activeRegionRef.current) activeRegionRef.current.play();
    else refs.wsRef.current?.play();
  }, [activeRegionRef, refs.wsRef]);

  return { addRegion, clearRegions, playRegion };
}
