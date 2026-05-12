import { useCallback, useEffect, useRef } from "react";

import type { DragToCreateOptions, QuickRetimeSelectionOptions, UseWaveSurferOptions, WaveSurferRefs, WaveSurferRegionsControls, WsRegion } from "./types";
import { WAVE_SURFER_DRAFT_REGION_COLOR, WAVE_SURFER_REGION_COLOR } from "./types";

const QUICK_RETIME_REGION_ID = "quick-retime-selection";
const QUICK_RETIME_REGION_COLOR = "rgba(59,130,246,0.18)";
const CREATE_LEXEME_REGION_ID = "create-lexeme-selection";

export function isQuickRetimeRegion(region: { id?: string } | null | undefined): boolean {
  return Boolean(region?.id?.startsWith(QUICK_RETIME_REGION_ID));
}

function isCreateLexemeRegion(region: { id?: string } | null | undefined): boolean {
  return Boolean(region?.id?.startsWith(CREATE_LEXEME_REGION_ID));
}

type DragSelectionRegionsPlugin = {
  enableDragSelection?: (options: { id: string; color: string; drag: boolean; resize: boolean }, threshold?: number) => (() => void) | void;
  on?: (event: "region-created" | "region-updated", handler: (region: WsRegion) => void) => (() => void) | void;
};

interface AttachRegionPathArgs {
  regions: DragSelectionRegionsPlugin;
  id: string;
  color: string;
  drag: boolean;
  resize: boolean;
  predicate: (region: WsRegion) => boolean;
  decorate?: (region: WsRegion) => void;
  onCreated?: (region: WsRegion) => void;
  onUpdated?: (region: WsRegion) => void;
  onContextMenu?: (region: WsRegion, event: MouseEvent) => void;
}

function attachRegionPath(args: AttachRegionPathArgs): () => void {
  const detachers: Array<() => void> = [];
  const disableSelection = args.regions.enableDragSelection?.(
    { id: args.id, color: args.color, drag: args.drag, resize: args.resize },
    1,
  );
  if (typeof disableSelection === "function") detachers.push(disableSelection);

  let detachCurrentContextMenu: (() => void) | null = null;
  const attachContextMenu = (region: WsRegion) => {
    detachCurrentContextMenu?.();
    detachCurrentContextMenu = null;
    if (!args.onContextMenu || !region.element) return;
    const handler = (event: MouseEvent) => {
      event.preventDefault();
      args.onContextMenu?.(region, event);
    };
    region.element.addEventListener("contextmenu", handler);
    detachCurrentContextMenu = () => region.element?.removeEventListener("contextmenu", handler);
  };

  const offCreated = args.regions.on?.("region-created", (region) => {
    if (!args.predicate(region)) return;
    args.decorate?.(region);
    attachContextMenu(region);
    args.onCreated?.(region);
  });
  if (typeof offCreated === "function") detachers.push(offCreated);

  if (args.onUpdated) {
    const offUpdated = args.regions.on?.("region-updated", (region) => {
      if (!args.predicate(region)) return;
      args.onUpdated?.(region);
    });
    if (typeof offUpdated === "function") detachers.push(offUpdated);
  }

  return () => {
    detachCurrentContextMenu?.();
    detachCurrentContextMenu = null;
    for (const detach of detachers.reverse()) detach();
  };
}

export function useWaveSurferRegions(
  refs: WaveSurferRefs,
  quickRetimeSelection?: UseWaveSurferOptions["quickRetimeSelection"],
): WaveSurferRegionsControls {
  const { regionsRef, activeRegionRef, clipEndRef, regionPrimedRef } = refs;
  const quickRetimeSelectionRef = useRef<QuickRetimeSelectionOptions | null>(null);
  const quickRetimeRegionRef = useRef<WsRegion | null>(null);
  const dragCreateRegionRef = useRef<WsRegion | null>(null);
  const dragCreateDisableSelectionRef = useRef<(() => void) | null>(null);
  const dragCreateUnsubscribeRef = useRef<Array<() => void>>([]);

  useEffect(() => {
    quickRetimeSelectionRef.current = quickRetimeSelection?.enabled ? quickRetimeSelection : null;
  }, [quickRetimeSelection]);

  const clearQuickRetimeSelection = useCallback(() => {
    quickRetimeRegionRef.current?.remove();
    quickRetimeRegionRef.current = null;
  }, []);

  const disableDragToCreate = useCallback(() => {
    for (const unsubscribe of dragCreateUnsubscribeRef.current) unsubscribe();
    dragCreateUnsubscribeRef.current = [];
    dragCreateDisableSelectionRef.current?.();
    dragCreateDisableSelectionRef.current = null;
    const region = dragCreateRegionRef.current;
    region?.remove();
    dragCreateRegionRef.current = null;
    if (region && activeRegionRef.current === region) activeRegionRef.current = null;
  }, [activeRegionRef]);

  const enableDragToCreate = useCallback((options: DragToCreateOptions) => {
    disableDragToCreate();
    const regions = regionsRef.current as unknown as DragSelectionRegionsPlugin | null;
    if (!regions?.enableDragSelection || !regions.on) return () => undefined;

    const rememberRegion = (region: WsRegion) => {
      if (dragCreateRegionRef.current && dragCreateRegionRef.current !== region) {
        dragCreateRegionRef.current.remove();
      }
      dragCreateRegionRef.current = region;
      activeRegionRef.current = region;
    };

    const teardown = attachRegionPath({
      regions,
      id: `${CREATE_LEXEME_REGION_ID}-${Date.now()}`,
      color: WAVE_SURFER_DRAFT_REGION_COLOR,
      drag: true,
      resize: true,
      predicate: isCreateLexemeRegion,
      onCreated: (region) => {
        rememberRegion(region);
        options.onRegionCreated({ start: region.start, end: region.end });
      },
      onUpdated: (region) => {
        rememberRegion(region);
        options.onRegionUpdated({ start: region.start, end: region.end });
      },
      onContextMenu: options.onContextMenu
        ? (region, event) => options.onContextMenu?.({ start: region.start, end: region.end }, event)
        : undefined,
    });
    dragCreateDisableSelectionRef.current = null;
    dragCreateUnsubscribeRef.current = [teardown];

    return disableDragToCreate;
  }, [activeRegionRef, disableDragToCreate, regionsRef]);

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
    const regions = regionsInstance as unknown as DragSelectionRegionsPlugin | null;
    const selection = quickRetimeSelectionRef.current;
    if (!regions?.enableDragSelection || !regions.on || !selection?.enabled) return;

    const teardown = attachRegionPath({
      regions,
      id: `${QUICK_RETIME_REGION_ID}-${Date.now()}`,
      color: QUICK_RETIME_REGION_COLOR,
      drag: false,
      resize: true,
      predicate: isQuickRetimeRegion,
      decorate: (region) => {
        if (quickRetimeRegionRef.current && quickRetimeRegionRef.current !== region) {
          quickRetimeRegionRef.current.remove();
        }
        quickRetimeRegionRef.current = region;
        region.element?.setAttribute("aria-label", selection.label);
        region.element?.setAttribute("title", selection.label);
      },
      onContextMenu: (region, event) => {
        const latest = quickRetimeSelectionRef.current;
        if (!latest?.enabled) return;
        latest.onContextMenu({ start: region.start, end: region.end }, event);
      },
    });

    return () => {
      teardown();
      clearQuickRetimeSelection();
    };
  }, [clearQuickRetimeSelection, regionsInstance, quickRetimeSelection]);

  const playRegion = useCallback(() => {
    if (activeRegionRef.current) activeRegionRef.current.play();
    else refs.wsRef.current?.play();
  }, [activeRegionRef, refs.wsRef]);

  return { addRegion, clearRegions, clearQuickRetimeSelection, enableDragToCreate, disableDragToCreate, playRegion };
}
