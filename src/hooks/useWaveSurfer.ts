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
  /**
   * Fires once when the user releases the mouse after a region drag or
   * resize — i.e. the final committed range. Callers that want to persist
   * region edits should hook this instead of `onRegionUpdate`, which
   * streams throughout the interaction.
   */
  onRegionCommit?: (start: number, end: number) => void;
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

  // When set, the next time `timeupdate` reports >= this time the wave is
  // paused and the ref is cleared. Used by `playClip` to make the default
  // play action stop at a lexeme boundary without bleeding into the next
  // word. Cleared on every pause / interaction so subsequent plays are
  // unbounded.
  const clipEndRef = useRef<number | null>(null);
  // True after `addRegion` until either the clip has played once or the
  // user has interacted with the waveform / pause control. Tells
  // `playClip` whether the next play should seek to the lexeme start
  // (first click after selecting a lexeme) or continue from the current
  // cursor position (subsequent click after the clip auto-stopped).
  const regionPrimedRef = useRef<boolean>(false);

  // -- Imperative controls (stable refs) --

  const play = useCallback(() => {
    clipEndRef.current = null;
    regionPrimedRef.current = false;
    wsRef.current?.play();
  }, []);
  const pause = useCallback(() => wsRef.current?.pause(), []);
  const playPause = useCallback(() => {
    if (!wsRef.current) return;
    if (wsRef.current.isPlaying()) {
      wsRef.current.pause();
    } else {
      clipEndRef.current = null;
      regionPrimedRef.current = false;
      wsRef.current.play();
    }
  }, []);

  /**
   * Play the active lexeme region. Behaviour depends on whether the
   * region is "primed" — true after `addRegion` until the clip has
   * played once or the user has touched the waveform:
   *
   * - **Primed** → seek to ``startSec`` and play, pausing automatically
   *   at ``endSec``. This is the user-visible "play just this lexeme"
   *   behaviour for the very first click after selecting a concept.
   * - **Not primed** → resume normal continuous playback from the
   *   current cursor position (which after the clip auto-stop is
   *   already at ``endSec``, so the audio continues into whatever
   *   follows).
   *
   * Returns true if the clip-bounded play actually started, false if
   * the call degraded to a plain play.
   */
  const playClip = useCallback((startSec: number, endSec: number) => {
    const ws = wsRef.current;
    if (!ws) return false;
    if (!regionPrimedRef.current || !Number.isFinite(endSec) || endSec <= 0) {
      // No fresh region (or invalid bounds) — behave like normal play.
      clipEndRef.current = null;
      ws.play();
      return false;
    }
    if (Number.isFinite(startSec) && startSec >= 0) {
      const dur = ws.getDuration();
      if (dur > 0) {
        ws.seekTo(clamp(startSec / dur, 0, 1));
      }
    }
    clipEndRef.current = endSec;
    regionPrimedRef.current = false; // consumed
    ws.play();
    return true;
  }, []);

  /**
   * Play a fixed [startSec, endSec] window and always auto-pause at endSec.
   * Unlike `playClip`, this ignores the region-primed flag and clip-bounds on
   * every call — so the bottom Play button (and Space hotkey) on a selected
   * region replays just that region even after waveform interaction cleared
   * the primed state.
   */
  const playRange = useCallback((startSec: number, endSec: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    if (!Number.isFinite(endSec) || endSec <= 0 || endSec <= startSec) {
      clipEndRef.current = null;
      ws.play();
      return;
    }
    const dur = ws.getDuration();
    if (dur > 0 && Number.isFinite(startSec) && startSec >= 0) {
      const cur = ws.getCurrentTime();
      if (cur < startSec - 0.01 || cur >= endSec - 0.01) {
        ws.seekTo(clamp(startSec / dur, 0, 1));
      }
    }
    clipEndRef.current = endSec;
    regionPrimedRef.current = false;
    ws.play();
  }, []);

  const seekToSec = useCallback((timeSec: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    const duration = ws.getDuration();
    if (!duration || duration <= 0) return;
    // Programmatic seeks (e.g. ParseUI auto-positions to lexeme start when
    // a concept is selected) do NOT consume the primed state — that's
    // what makes the next Play press jump to the lexeme start. The clip
    // end target IS cleared, since the new cursor position invalidates
    // any in-flight bounded play. User-initiated waveform clicks come
    // through the wavesurfer "interaction" event below and clear both.
    clipEndRef.current = null;
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

  /**
   * Scroll the waveform so that `timeSec` is positioned at `fraction` of the
   * visible viewport width (e.g. 0.33 = one-third from the left). Useful when
   * seeking to a lexeme start — centering hides the trailing audio, whereas
   * 33% offset keeps more of the following waveform visible for region edits.
   */
  const scrollToTimeAtFraction = useCallback((timeSec: number, fraction: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    const duration = ws.getDuration();
    if (!duration || duration <= 0) return;
    const options = (ws as unknown as { options: { minPxPerSec?: number } }).options;
    const pxPerSec = options?.minPxPerSec ?? 0;
    if (!pxPerSec) return;
    const wrapper = ws.getWrapper();
    const viewport = wrapper?.parentElement;
    const viewportWidth = viewport?.clientWidth ?? 0;
    if (!viewportWidth) return;
    const totalPx = duration * pxPerSec;
    const maxScroll = Math.max(0, totalPx - viewportWidth);
    const target = clamp(timeSec * pxPerSec - viewportWidth * fraction, 0, maxScroll);
    ws.setScroll(target);
  }, []);

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
      // Adding a region (i.e. selecting a lexeme) primes the next Play
      // press to seek-to-start + clip-bound. Cleared by playClip itself,
      // any waveform interaction, or pause/finish.
      regionPrimedRef.current = true;
      clipEndRef.current = null;
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

    // Skip initialization when the audio URL isn't ready yet. Otherwise
    // WaveSurfer.load("") throws and leaves the component in a broken state.
    // Re-runs when audioUrl changes.
    if (!options.audioUrl) return;

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
      const stopAt = clipEndRef.current;
      if (stopAt !== null && t >= stopAt) {
        clipEndRef.current = null;
        ws.pause();
      }
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
      // Manual pause (or our own clip-bounded pause) discards any pending
      // clip-end and primed state so the next play resumes normal
      // continuous playback from wherever the cursor landed.
      clipEndRef.current = null;
      regionPrimedRef.current = false;
      options.onPlayStateChange?.(false);
      usePlaybackStore.setState({ isPlaying: false });
    });

    ws.on("finish", () => {
      clipEndRef.current = null;
      regionPrimedRef.current = false;
      options.onPlayStateChange?.(false);
      usePlaybackStore.setState({ isPlaying: false });
    });

    ws.on("interaction", () => {
      // Clicking on the waveform itself triggers wavesurfer's built-in
      // seek; that's a "user moved elsewhere" signal — clear the primed
      // state and any pending clip-bound so the next Play resumes normal
      // continuous playback instead of jumping back to the lexeme start.
      clipEndRef.current = null;
      regionPrimedRef.current = false;
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

    // `region-updated` in the wavesurfer regions plugin fires continuously
    // while the user drags or resizes. The public type map doesn't include a
    // "drag end" event, so we attach a pointerup listener to the container
    // and treat the region's current bounds as the committed value.
    function onCommit() {
      const active = activeRegionRef.current;
      if (!active) return;
      options.onRegionCommit?.(active.start, active.end);
    }
    container.addEventListener("pointerup", onCommit);

    // -- Keyboard shortcuts (scoped to container) --

    function onKeyDown(e: KeyboardEvent) {
      if (isInteractiveTarget(e.target)) return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          ws.playPause();
          break;
      }
    }

    function onWheel(e: WheelEvent) {
      if (isInteractiveTarget(e.target)) return;

      const typedWs = ws as unknown as {
        getWrapper?: () => HTMLElement;
        setScroll?: (pixels: number) => void;
      };
      const wrapper = typedWs.getWrapper?.();
      const viewport = wrapper?.parentElement;
      if (!viewport) return;

      const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (!delta) return;

      e.preventDefault();
      const nextScroll = Math.max(0, viewport.scrollLeft + delta);
      viewport.scrollLeft = nextScroll;
      typedWs.setScroll?.(nextScroll);
    }

    container.addEventListener("keydown", onKeyDown);
    container.addEventListener("wheel", onWheel, { passive: false });

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
      container.removeEventListener("wheel", onWheel);
      container.removeEventListener("pointerup", onCommit);
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
      activeRegionRef.current = null;
      clipEndRef.current = null;
      regionPrimedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.audioUrl, options.peaksUrl, options.initialSeekSec]);

  return {
    play,
    pause,
    playPause,
    playClip,
    playRange,
    seek,
    scrollToTimeAtFraction,
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
