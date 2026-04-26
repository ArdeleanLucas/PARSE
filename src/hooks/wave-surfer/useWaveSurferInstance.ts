import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";
import TimelinePlugin from "wavesurfer.js/dist/plugins/timeline.js";

import { usePlaybackStore } from "../../stores/playbackStore";

import { loadWaveSurferAudio } from "./useWaveSurferPeaks";
import { isInteractiveTarget, clamp } from "./useWaveSurferPlayback";
import type { UseWaveSurferOptions, WaveSurferRefs } from "./types";

export function useWaveSurferInstance(
  options: UseWaveSurferOptions,
  refs: WaveSurferRefs,
) {
  const { wsRef, regionsRef, activeRegionRef, abortControllerRef, clipEndRef, regionPrimedRef } = refs;
  const callbacksRef = useRef({
    onTimeUpdate: options.onTimeUpdate,
    onReady: options.onReady,
    onPlayStateChange: options.onPlayStateChange,
    onRegionUpdate: options.onRegionUpdate,
    onRegionCommit: options.onRegionCommit,
  });

  useEffect(() => {
    callbacksRef.current = {
      onTimeUpdate: options.onTimeUpdate,
      onReady: options.onReady,
      onPlayStateChange: options.onPlayStateChange,
      onRegionUpdate: options.onRegionUpdate,
      onRegionCommit: options.onRegionCommit,
    };
  }, [options.onTimeUpdate, options.onReady, options.onPlayStateChange, options.onRegionUpdate, options.onRegionCommit]);

  useEffect(() => {
    const container = options.containerRef.current;
    if (!container || !options.audioUrl) return;

    abortControllerRef.current?.abort();
    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;
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

    ws.on("timeupdate", (time: number) => {
      const stopAt = clipEndRef.current;
      if (stopAt !== null && time >= stopAt) {
        clipEndRef.current = null;
        ws.pause();
      }
      callbacksRef.current.onTimeUpdate?.(time);
      usePlaybackStore.setState({ currentTime: time });
    });

    ws.on("ready", () => {
      const duration = ws.getDuration();
      callbacksRef.current.onReady?.(duration);
      usePlaybackStore.setState({ duration });
      if (options.initialSeekSec && options.initialSeekSec > 0 && duration > 0) {
        ws.seekTo(clamp(options.initialSeekSec / duration, 0, 1));
      }
    });

    ws.on("play", () => {
      callbacksRef.current.onPlayStateChange?.(true);
      usePlaybackStore.setState({ isPlaying: true });
    });

    ws.on("pause", () => {
      clipEndRef.current = null;
      regionPrimedRef.current = false;
      callbacksRef.current.onPlayStateChange?.(false);
      usePlaybackStore.setState({ isPlaying: false });
    });

    ws.on("finish", () => {
      clipEndRef.current = null;
      regionPrimedRef.current = false;
      callbacksRef.current.onPlayStateChange?.(false);
      usePlaybackStore.setState({ isPlaying: false });
    });

    ws.on("interaction", () => {
      clipEndRef.current = null;
      regionPrimedRef.current = false;
    });

    regions.on("region-created", (region) => {
      if (activeRegionRef.current && activeRegionRef.current !== region) activeRegionRef.current.remove();
      activeRegionRef.current = region;
    });

    regions.on("region-updated", (region) => {
      activeRegionRef.current = region;
      callbacksRef.current.onRegionUpdate?.(region.start, region.end);
    });

    const onCommit = () => {
      const active = activeRegionRef.current;
      if (!active) return;
      callbacksRef.current.onRegionCommit?.(active.start, active.end);
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (isInteractiveTarget(e.target)) return;
      if (e.key === " ") {
        e.preventDefault();
        ws.playPause();
      }
    };

    const onWheel = (e: WheelEvent) => {
      if (isInteractiveTarget(e.target)) return;
      const typedWs = ws as unknown as { getWrapper?: () => HTMLElement; setScroll?: (pixels: number) => void };
      const viewport = typedWs.getWrapper?.()?.parentElement;
      if (!viewport) return;
      const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (!delta) return;
      e.preventDefault();
      const nextScroll = Math.max(0, viewport.scrollLeft + delta);
      viewport.scrollLeft = nextScroll;
      typedWs.setScroll?.(nextScroll);
    };

    container.addEventListener("pointerup", onCommit);
    container.addEventListener("keydown", onKeyDown);
    container.addEventListener("wheel", onWheel, { passive: false });
    void loadWaveSurferAudio(ws, options, abortCtrl);

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
  }, [
    options.audioUrl,
    options.peaksUrl,
    options.initialSeekSec,
    options.durationSec,
    options.containerRef,
    abortControllerRef,
    activeRegionRef,
    clipEndRef,
    regionPrimedRef,
    regionsRef,
    wsRef,
  ]);
}
