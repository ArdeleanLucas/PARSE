import { useCallback, useEffect, useRef } from "react";

import type { QuickRetimeSelectionOptions, UseWaveSurferOptions, WaveSurferRefs, WaveSurferRegionsControls, WsRegion } from "./types";
import { WAVE_SURFER_REGION_COLOR } from "./types";

const QUICK_RETIME_REGION_ID = "quick-retime-selection";
const QUICK_RETIME_REGION_COLOR = "rgba(59,130,246,0.18)";

export function isQuickRetimeRegion(region: { id?: string } | null | undefined): boolean {
  return Boolean(region?.id?.startsWith(QUICK_RETIME_REGION_ID));
}

export function useWaveSurferRegions(
  refs: WaveSurferRefs,
  quickRetimeSelection?: UseWaveSurferOptions["quickRetimeSelection"],
): WaveSurferRegionsControls {
  const { regionsRef, activeRegionRef, clipEndRef, regionPrimedRef } = refs;
  const quickRetimeSelectionRef = useRef<QuickRetimeSelectionOptions | null>(null);
  const quickRetimeRegionRef = useRef<WsRegion | null>(null);

  useEffect(() => {
    quickRetimeSelectionRef.current = quickRetimeSelection?.enabled ? quickRetimeSelection : null;
  }, [quickRetimeSelection]);

  const clearQuickRetimeSelection = useCallback(() => {
    quickRetimeRegionRef.current?.remove();
    quickRetimeRegionRef.current = null;
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !quickRetimeRegionRef.current) return;
      event.preventDefault();
      clearQuickRetimeSelection();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clearQuickRetimeSelection]);

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

  const regionsInstance = regionsRef.current;

  useEffect(() => {
    const regions = regionsInstance as unknown as {
      enableDragSelection?: (options: { id: string; color: string; drag: boolean; resize: boolean }, threshold?: number) => () => void;
      on?: (event: "region-created", handler: (region: WsRegion) => void) => () => void;
    } | null;
    const selection = quickRetimeSelectionRef.current;
    if (!regions?.enableDragSelection || !regions.on || !selection?.enabled) return;

    const disableDragSelection = regions.enableDragSelection(
      {
        id: `${QUICK_RETIME_REGION_ID}-${Date.now()}`,
        color: QUICK_RETIME_REGION_COLOR,
        drag: false,
        resize: true,
      },
      1,
    );

    const unsubscribe = regions.on("region-created", (region) => {
      if (!isQuickRetimeRegion(region)) return;
      if (quickRetimeRegionRef.current && quickRetimeRegionRef.current !== region) {
        quickRetimeRegionRef.current.remove();
      }
      quickRetimeRegionRef.current = region;
      region.element?.setAttribute("aria-label", selection.label);
      region.element?.setAttribute("title", selection.label);
      region.element?.addEventListener("contextmenu", (event) => {
        const latest = quickRetimeSelectionRef.current;
        if (!latest?.enabled) return;
        event.preventDefault();
        latest.onContextMenu({ start: region.start, end: region.end }, event);
      });
    });

    return () => {
      unsubscribe?.();
      disableDragSelection?.();
      clearQuickRetimeSelection();
    };
  }, [clearQuickRetimeSelection, regionsInstance, quickRetimeSelection]);

  const playRegion = useCallback(() => {
    if (activeRegionRef.current) activeRegionRef.current.play();
    else refs.wsRef.current?.play();
  }, [activeRegionRef, refs.wsRef]);

  return { addRegion, clearRegions, clearQuickRetimeSelection, playRegion };
}
