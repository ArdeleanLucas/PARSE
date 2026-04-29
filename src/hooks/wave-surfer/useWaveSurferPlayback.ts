import { useCallback } from "react";

import type { WaveSurferControls, WaveSurferRefs } from "./types";

export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

export function isInteractiveTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select" || tag === "button") return true;
  return Boolean((target as HTMLElement).isContentEditable);
}

export function useWaveSurferPlayback(refs: WaveSurferRefs): WaveSurferControls {
  const { wsRef, clipEndRef, regionPrimedRef } = refs;

  const play = useCallback(() => {
    clipEndRef.current = null;
    regionPrimedRef.current = false;
    wsRef.current?.play();
  }, [clipEndRef, regionPrimedRef, wsRef]);

  const pause = useCallback(() => wsRef.current?.pause(), [wsRef]);

  const playPause = useCallback(() => {
    const ws = wsRef.current;
    if (!ws) return;
    if (ws.isPlaying()) {
      ws.pause();
      return;
    }
    clipEndRef.current = null;
    regionPrimedRef.current = false;
    ws.play();
  }, [clipEndRef, regionPrimedRef, wsRef]);

  const playClip = useCallback((startSec: number, endSec: number) => {
    const ws = wsRef.current;
    if (!ws) return false;
    if (!regionPrimedRef.current || !Number.isFinite(endSec) || endSec <= 0) {
      clipEndRef.current = null;
      ws.play();
      return false;
    }
    if (Number.isFinite(startSec) && startSec >= 0) {
      const dur = ws.getDuration();
      if (dur > 0) ws.seekTo(clamp(startSec / dur, 0, 1));
    }
    clipEndRef.current = endSec;
    regionPrimedRef.current = false;
    ws.play();
    return true;
  }, [clipEndRef, regionPrimedRef, wsRef]);

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
      if (cur < startSec - 0.01 || cur >= endSec - 0.01) ws.seekTo(clamp(startSec / dur, 0, 1));
    }
    clipEndRef.current = endSec;
    regionPrimedRef.current = false;
    ws.play();
  }, [clipEndRef, regionPrimedRef, wsRef]);

  const seekToSec = useCallback((timeSec: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    const duration = ws.getDuration();
    if (!duration || duration <= 0) return;
    clipEndRef.current = null;
    ws.seekTo(clamp(timeSec / duration, 0, 1));
  }, [clipEndRef, wsRef]);

  const seek = useCallback((t: number) => seekToSec(t), [seekToSec]);
  const skip = useCallback((delta: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    seekToSec(ws.getCurrentTime() + delta);
  }, [seekToSec, wsRef]);
  const jump = useCallback((delta: number) => {
    const ws = wsRef.current;
    if (!ws) return;
    seekToSec(ws.getCurrentTime() + delta);
  }, [seekToSec, wsRef]);

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
    ws.setScroll(clamp(timeSec * pxPerSec - viewportWidth * fraction, 0, maxScroll));
  }, [wsRef]);

  const setZoom = useCallback((minPxPerSec: number) => wsRef.current?.zoom(minPxPerSec), [wsRef]);
  const setRate = useCallback((rate: number) => wsRef.current?.setPlaybackRate(rate), [wsRef]);
  const setVolume = useCallback((volume: number) => wsRef.current?.setVolume(volume), [wsRef]);

  return { play, pause, playPause, playClip, playRange, seek, scrollToTimeAtFraction, skip, jump, setZoom, setRate, setVolume };
}
