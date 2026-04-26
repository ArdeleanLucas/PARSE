import { useCallback, useEffect, useMemo, useRef } from "react";

import { useAnnotationSync } from "../../../hooks/useAnnotationSync";
import { useWaveSurfer } from "../../../hooks/useWaveSurfer";
import { useAnnotationStore } from "../../../stores/annotationStore";
import { useConfigStore } from "../../../stores/configStore";
import { usePlaybackStore } from "../../../stores/playbackStore";
import { useUIStore } from "../../../stores/uiStore";
import { deriveAudioUrl } from "../../../lib/parseUIUtils";

export function useAnnotateLifecycle(containerRef: React.RefObject<HTMLDivElement>) {
  const load = useConfigStore((s) => s.load);
  const speakers = useConfigStore((s) => s.config?.speakers ?? []);
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const annotatePanel = useUIStore((s) => s.annotatePanel);
  const onboardingComplete = useUIStore((s) => s.onboardingComplete);
  const setActiveSpeaker = useUIStore((s) => s.setActiveSpeaker);
  const setAnnotatePanel = useUIStore((s) => s.setAnnotatePanel);
  const setOnboardingComplete = useUIStore((s) => s.setOnboardingComplete);
  const dirty = useAnnotationStore((s) => s.dirty);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? s.records[activeSpeaker] ?? null : null,
  );
  const history = useAnnotationStore((s) =>
    activeSpeaker ? s.histories[activeSpeaker] ?? null : null,
  );
  const undo = useAnnotationStore((s) => s.undo);
  const redo = useAnnotationStore((s) => s.redo);

  const setPlaybackSpeaker = usePlaybackStore((s) => s.setActiveSpeaker);
  const zoom = usePlaybackStore((s) => s.zoom);
  const setZoom = usePlaybackStore((s) => s.setZoom);
  const loopEnabled = usePlaybackStore((s) => s.loopEnabled);
  const toggleLoop = usePlaybackStore((s) => s.toggleLoop);
  const playbackRate = usePlaybackStore((s) => s.playbackRate);
  const setPlaybackRate = usePlaybackStore((s) => s.setPlaybackRate);
  const currentTime = usePlaybackStore((s) => s.currentTime);
  const playbackDuration = usePlaybackStore((s) => s.duration);

  const canUndo = (history?.undo.length ?? 0) > 0;
  const canRedo = (history?.redo.length ?? 0) > 0;
  const nextUndoLabel = canUndo ? history!.undo[history!.undo.length - 1].label : "";
  const nextRedoLabel = canRedo ? history!.redo[history!.redo.length - 1].label : "";

  useAnnotationSync();

  const audioUrl = useMemo(() => deriveAudioUrl(record), [record]);

  const waveform = useWaveSurfer({
    containerRef,
    audioUrl,
    peaksUrl: activeSpeaker ? `/peaks/${activeSpeaker}.json` : undefined,
    onTimeUpdate: (t) => usePlaybackStore.setState({ currentTime: t }),
    onReady: (d) => usePlaybackStore.setState({ duration: d }),
    onPlayStateChange: (p) => usePlaybackStore.setState({ isPlaying: p }),
    onRegionUpdate: (start, end) =>
      usePlaybackStore.setState({ selectedRegion: { start, end } }),
  });

  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  const handleSpeakerClick = useCallback(
    (speaker: string) => {
      setActiveSpeaker(speaker);
      setPlaybackSpeaker(speaker);
    },
    [setActiveSpeaker, setPlaybackSpeaker],
  );

  const handleOnboardingComplete = useCallback(() => {
    setOnboardingComplete(true);
  }, [setOnboardingComplete]);

  const handleZoomChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      setZoom(val);
      waveform.setZoom(val);
    },
    [setZoom, waveform],
  );

  const handleRateChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const rate = Number(e.target.value);
      setPlaybackRate(rate);
      waveform.setRate(rate);
    },
    [setPlaybackRate, waveform],
  );

  const handleSeekWithRegion = useCallback(
    (t: number, create?: boolean, dur?: number) => {
      waveform.seek(t);
      if (create) waveform.addRegion(t, t + (dur ?? 3));
    },
    [waveform],
  );

  const handleUndo = useCallback(() => {
    if (!activeSpeaker) return null;
    return undo(activeSpeaker);
  }, [activeSpeaker, undo]);

  const handleRedo = useCallback(() => {
    if (!activeSpeaker) return null;
    return redo(activeSpeaker);
  }, [activeSpeaker, redo]);

  useEffect(() => {
    if (!activeSpeaker) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        if (target.isContentEditable) return;
      }
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((key === "z" && e.shiftKey) || key === "y") {
        e.preventDefault();
        handleRedo();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [activeSpeaker, handleUndo, handleRedo]);

  const waveformContainerTestId = useRef("waveform-container");

  return {
    activeConcept,
    activeSpeaker,
    annotatePanel,
    audioUrl,
    canRedo,
    canUndo,
    currentTime,
    dirty,
    handleOnboardingComplete,
    handleRateChange,
    handleRedo,
    handleSeekWithRegion,
    handleSpeakerClick,
    handleUndo,
    handleZoomChange,
    loopEnabled,
    nextRedoLabel,
    nextUndoLabel,
    onboardingComplete,
    playbackDuration,
    playbackRate,
    record,
    setAnnotatePanel,
    speakers,
    toggleLoop,
    waveform,
    waveformContainerTestId: waveformContainerTestId.current,
    zoom,
  };
}
