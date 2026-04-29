import type { RefObject, MutableRefObject } from "react";
import type WaveSurfer from "wavesurfer.js";
import type RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";

export interface PeaksJson {
  data: number[] | number[][];
  channels?: number;
}

export interface QuickRetimeSelection {
  start: number;
  end: number;
}

export interface QuickRetimeSelectionOptions {
  enabled: boolean;
  label: string;
  onContextMenu: (selection: QuickRetimeSelection, event: MouseEvent) => void;
}

export interface UseWaveSurferOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  audioUrl: string;
  peaksUrl?: string;
  initialSeekSec?: number;
  durationSec?: number;
  onRegionUpdate?: (start: number, end: number) => void;
  onRegionCommit?: (start: number, end: number) => void;
  onTimeUpdate?: (time: number) => void;
  onReady?: (duration: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  quickRetimeSelection?: QuickRetimeSelectionOptions | null;
}

export interface WsRegion {
  id: string;
  start: number;
  end: number;
  element?: HTMLElement | null;
  play: () => void;
  remove: () => void;
}

export interface WaveSurferRefs {
  wsRef: MutableRefObject<WaveSurfer | null>;
  regionsRef: MutableRefObject<RegionsPlugin | null>;
  activeRegionRef: MutableRefObject<WsRegion | null>;
  abortControllerRef: MutableRefObject<AbortController | null>;
  clipEndRef: MutableRefObject<number | null>;
  regionPrimedRef: MutableRefObject<boolean>;
}

export interface WaveSurferControls {
  play: () => void;
  pause: () => void;
  playPause: () => void;
  playClip: (startSec: number, endSec: number) => boolean;
  playRange: (startSec: number, endSec: number) => void;
  seek: (t: number) => void;
  scrollToTimeAtFraction: (timeSec: number, fraction: number) => void;
  skip: (delta: number) => void;
  jump: (delta: number) => void;
  setZoom: (minPxPerSec: number) => void;
  setRate: (rate: number) => void;
}

export interface WaveSurferRegionsControls {
  addRegion: (start: number, end: number, id?: string) => void;
  clearRegions: () => void;
  clearQuickRetimeSelection: () => void;
  playRegion: () => void;
}

export interface UseWaveSurferResult extends WaveSurferControls, WaveSurferRegionsControls {
  wsRef: MutableRefObject<WaveSurfer | null>;
  regionsRef: MutableRefObject<RegionsPlugin | null>;
}

export const WAVE_SURFER_REGION_COLOR = "rgba(255,165,0,0.22)";
