import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.js";
import { useEffect, useRef, useCallback } from "react";
import { usePlaybackStore } from "../stores/playbackStore";

// ---------- Types ----------

interface PeaksJson {
  data: number[] | number[][];
  channels?: number;
}

interface UseWaveSurferOptions {
  containerRef: React.RefObject<HTMLDivElement | null>;
  audioUrl: string;
  peaksUrl?: string;
  initialSeekSec?: number;
  durationSec?: number;
  onRegionUpdate?: (start: number, end: number) => void;
  onTimeUpdate?: (time: number) => void;
  onReady?: (duration: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
}

// WaveSurfer region object — wavesurfer.js v7 doesn't export a Region type
interface WsRegion {
  id: string;
  start: number;
  end: number;
  play: () => void;
  remove: () => void;
}

// ---------- Helpers ----------

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") return true;
  if ((target as HTMLElement).isContentEditable) return true;
  return false;
}

function getChannelDataFromPeaks(peaks: PeaksJson): number[][] | undefined {
  if (peaks.data == null) return undefined;

  const channels = Number(peaks.channels);
  const data = peaks.data;

  if (!Number.isFinite(channels) || channels <= 1) {
    return [data as number[]];
  }

  if (
    Array.isArray(data) &&
    data.length === channels &&
    data.every((ch) => Array.isArray(ch))
  ) {
    return data as number[][];
  }

  console.warn("[useWaveSurfer] Unsupported multi-channel peaks payload; loading without peaks.");
  return undefined;
}

// ---------- Hook ----------

export function useWaveSurfer(options: UseWaveSurferOptions) {
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<RegionsPlugin | null>(null);
  const activeRegionRef = useRef<WsRegion | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // -- Imperative controls (stable refs) --

  const play = useCallback(() => wsRef.current?.play(), []);
  const pause = useCallback(() => wsRef.current?.pause(), []);
  const playPause = useCallback(() => wsRef.current?.playPause(), []);

  const seekToSec = useCallback((timeSec: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    const duration = ws.getDuration();
    if (!duration || duration <= 0) return;
    ws.seekTo(clamp(timeSec / duration, 0, 1));
  }, []);

  const seek = useCallback(
    (t: number) => seekToSec(t),
    [seekToSec],
  );

  const skip = useCallback(
    (delta: number) => {
      const ws = wsRef.current;
      if (!ws) return;
      seekToSec(ws.getCurrentTime() + delta);
    },
    [seekToSec],
  );

  const jump = useCallback(
    (delta: number) => {
      const ws = wsRef.current;
      if (!ws) return;
      seekToSec(ws.getCurrentTime() + delta);
    },
    [seekToSec],
  );

  const setZoom = useCallback((minPxPerSec: number) => {
    wsRef.current?.zoom(minPxPerSec);
  }, []);

  const setRate = useCallback((rate: number) => {
    wsRef.current?.setPlaybackRate(rate);
  }, []);

  const clearRegions = useCallback(() => {
    activeRegionRef.current?.remove();
    activeRegionRef.current = null;
  }, []);

  const addRegion = useCallback(
    (start: number, end: number, id?: string) => {
      clearRegions();
      if (!regionsRef.current) return;
      const region = regionsRef.current.addRegion({
        start,
        end,
        id: id ?? `r-${start}`,
        color: "rgba(255,165,0,0.22)",
        drag: true,
        resize: true,
      }) as unknown as WsRegion;
      activeRegionRef.current = region;
    },
    [clearRegions],
  );

  const playRegion = useCallback(() => {
    if (activeRegionRef.current) {
      activeRegionRef.current.play();
    } else {
      wsRef.current?.play();
    }
  }, []);

  // -- Main effect --

  useEffect(() => {
    const container = options.containerRef.current;
    if (!container) return;

    // Abort any previous peaks fetch
    abortControllerRef.current?.abort();
    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    // Set up keyboard focus
    container.tabIndex = 0;

    const regions = RegionsPlugin.create();
    const timeline = TimelinePlugin.create({ container });

    const ws = WaveSurfer.create({
      container,
      waveColor: "#4a9eff",
      progressColor: "#1a5fbd",
      cursorColor: "#ff6b35",
      height: 80,
      normalize: true,
      plugins: [regions, timeline],
    });

    wsRef.current = ws;
    regionsRef.current = regions;
    activeRegionRef.current = null;

    // -- Store sync & callbacks --

    ws.on("timeupdate", (t: number) => {
      options.onTimeUpdate?.(t);
      usePlaybackStore.setState({ currentTime: t });
    });

    ws.on("ready", () => {
      const d = ws.getDuration();
      options.onReady?.(d);
      usePlaybackStore.setState({ duration: d });

      // Initial seek
      if (options.initialSeekSec && options.initialSeekSec > 0) {
        const dur = ws.getDuration();
        if (dur > 0) {
          ws.seekTo(clamp(options.initialSeekSec / dur, 0, 1));
        }
      }
    });

    ws.on("play", () => {
      options.onPlayStateChange?.(true);
      usePlaybackStore.setState({ isPlaying: true });
    });

    ws.on("pause", () => {
      options.onPlayStateChange?.(false);
      usePlaybackStore.setState({ isPlaying: false });
    });

    ws.on("finish", () => {
      options.onPlayStateChange?.(false);
      usePlaybackStore.setState({ isPlaying: false });
    });

    // -- Region events --

    regions.on("region-created", (region: WsRegion) => {
      if (activeRegionRef.current && activeRegionRef.current !== region) {
        activeRegionRef.current.remove();
      }
      activeRegionRef.current = region;
    });

    regions.on("region-updated", (region: WsRegion) => {
      activeRegionRef.current = region;
      options.onRegionUpdate?.(region.start, region.end);
    });

    // -- Keyboard shortcuts (scoped to container) --

    function onKeyDown(e: KeyboardEvent) {
      if (isInteractiveTarget(e.target)) return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          ws.playPause();
          break;
        case "ArrowLeft":
          e.preventDefault();
          {
            const dur = ws.getDuration();
            if (dur > 0) {
              const delta = e.shiftKey ? -5 : -1;
              ws.seekTo(clamp((ws.getCurrentTime() + delta) / dur, 0, 1));
            }
          }
          break;
        case "ArrowRight":
          e.preventDefault();
          {
            const dur = ws.getDuration();
            if (dur > 0) {
              const delta = e.shiftKey ? 5 : 1;
              ws.seekTo(clamp((ws.getCurrentTime() + delta) / dur, 0, 1));
            }
          }
          break;
      }
    }

    container.addEventListener("keydown", onKeyDown);

    // -- Load audio (with optional peaks) --

    async function loadAudio() {
      if (options.peaksUrl) {
        try {
          const resp = await fetch(options.peaksUrl, { signal: abortCtrl.signal });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const peaksJson = (await resp.json()) as PeaksJson;
          const channelData = getChannelDataFromPeaks(peaksJson);
          if (channelData) {
            ws.load(options.audioUrl, channelData, options.durationSec);
          } else {
            ws.load(options.audioUrl);
          }
        } catch (err: unknown) {
          if (err instanceof DOMException && err.name === "AbortError") return;
          console.warn("[useWaveSurfer] Peaks fetch failed, loading without peaks:", err);
          ws.load(options.audioUrl);
        }
      } else {
        ws.load(options.audioUrl);
      }
    }

    loadAudio();

    // -- Cleanup --

    return () => {
      abortControllerRef.current?.abort();
      container.removeEventListener("keydown", onKeyDown);
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
      activeRegionRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.audioUrl, options.peaksUrl, options.initialSeekSec]);

  return {
    play,
    pause,
    playPause,
    seek,
    skip,
    jump,
    setZoom,
    setRate,
    addRegion,
    clearRegions,
    playRegion,
    wsRef,
    regionsRef,
  };
}
