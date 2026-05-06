import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Anchor,
  Check,
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  Redo2,
  Save,
  SkipBack,
  SkipForward,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import { useSpectrogram } from "../../../hooks/useSpectrogram";
import { useWaveSurfer } from "../../../hooks/useWaveSurfer";
import { LEXEME_SCOPE_TIERS } from "../../../stores/annotation/actions";
import { useAnnotationStore } from "../../../stores/annotationStore";
import { usePlaybackStore } from "../../../stores/playbackStore";
import { useSpectrogramSettings } from "../../../stores/useSpectrogramSettings";
import { saveLexemeNote } from "../../../api/client";
import { LABEL_COL_PX, TranscriptionLanes } from "../TranscriptionLanes";
import { SpectrogramSettings } from "../SpectrogramSettings";

import { SpeakerHeader } from "./SpeakerHeader";
import { findAnnotationForConcept, formatPlaybackTime, formatPlayhead, pickOrthoIntervalForConcept } from "./shared";
import type { AnnotateViewProps } from "./types";

export { pickOrthoIntervalForConcept };

const SPEC_HEIGHT = 180;

export const AnnotateView: React.FC<AnnotateViewProps> = ({
  concept,
  speaker,
  totalConcepts,
  onPrev,
  onNext,
  audioUrl,
  peaksUrl,
  onCaptureOffsetAnchor,
  captureToast,
}) => {
  const record = useAnnotationStore((s) => s.records[speaker] ?? null);
  const moveIntervalAcrossTiers = useAnnotationStore((s) => s.moveIntervalAcrossTiers);
  const saveLexemeAnnotation = useAnnotationStore((s) => s.saveLexemeAnnotation);
  const saveSpeaker = useAnnotationStore((s) => s.saveSpeaker);
  const undoAnnotation = useAnnotationStore((s) => s.undo);
  const redoAnnotation = useAnnotationStore((s) => s.redo);
  const undoRedoHistory = useAnnotationStore((s) => s.histories[speaker] ?? null);
  const canUndo = (undoRedoHistory?.undo.length ?? 0) > 0;
  const canRedo = (undoRedoHistory?.redo.length ?? 0) > 0;
  const nextUndoLabel = canUndo ? undoRedoHistory!.undo[undoRedoHistory!.undo.length - 1].label : "";
  const nextRedoLabel = canRedo ? undoRedoHistory!.redo[undoRedoHistory!.redo.length - 1].label : "";
  const [undoToast, setUndoToast] = useState<string | null>(null);
  useEffect(() => {
    if (!undoToast) return;
    const timeout = window.setTimeout(() => setUndoToast(null), 2200);
    return () => window.clearTimeout(timeout);
  }, [undoToast]);

  const handleUndo = useCallback(() => {
    const label = undoAnnotation(speaker);
    if (label) setUndoToast(`Undid ${label}`);
  }, [speaker, undoAnnotation]);

  const handleRedo = useCallback(() => {
    const label = redoAnnotation(speaker);
    if (label) setUndoToast(`Redid ${label}`);
  }, [speaker, redoAnnotation]);

  useEffect(() => {
    if (!speaker) return;
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
  }, [speaker, handleUndo, handleRedo]);

  const setConceptTag = useAnnotationStore((s) => s.setConceptTag);
  const setConfirmedAnchor = useAnnotationStore((s) => s.setConfirmedAnchor);
  const isConfirmed = Boolean(record?.concept_tags?.[concept.key]?.includes("confirmed"));
  const confirmedAnchor = record?.confirmed_anchors?.[concept.key] ?? null;
  const { conceptInterval, ipaInterval, orthoInterval, directOrthoInterval } = useMemo(
    () => findAnnotationForConcept(record, concept),
    [record, concept],
  );

  // Past-end-of-audio detection. The annotation can carry intervals whose
  // timestamps land beyond `source_audio_duration_sec` — e.g. Khan01's
  // manifest is built against the [file1+file2+file3] concat (12665s) but
  // the working WAV is only the third file (8590s) until the concat lands.
  // Surface a per-speaker banner and disable seek/play for the current
  // concept when its interval starts past EOA.
  const sourceAudioDurationSec = record?.source_audio_duration_sec ?? null;
  const currentConceptPastEoa = useMemo(() => {
    if (!conceptInterval || typeof sourceAudioDurationSec !== 'number' || sourceAudioDurationSec <= 0) return false;
    if (typeof conceptInterval.start === 'number' && conceptInterval.start >= sourceAudioDurationSec) return true;
    if (typeof conceptInterval.end === 'number' && conceptInterval.end > sourceAudioDurationSec) return true;
    return false;
  }, [conceptInterval, sourceAudioDurationSec]);
  const pastEoaSummary = useMemo(() => {
    const intervals = record?.tiers.concept?.intervals ?? [];
    if (typeof sourceAudioDurationSec !== 'number' || sourceAudioDurationSec <= 0) {
      return { total: intervals.length, pastEoa: 0 };
    }
    let pastEoa = 0;
    for (const iv of intervals) {
      const startPast = typeof iv.start === 'number' && iv.start >= sourceAudioDurationSec;
      const endPast = typeof iv.end === 'number' && iv.end > sourceAudioDurationSec;
      if (startPast || endPast) pastEoa += 1;
    }
    return { total: intervals.length, pastEoa };
  }, [record, sourceAudioDurationSec]);
  const formatDurationHuman = (sec: number): string => {
    if (!Number.isFinite(sec) || sec <= 0) return '0s';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec - m * 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };
  const [pastEoaToast, setPastEoaToast] = useState<string | null>(null);
  useEffect(() => {
    if (!pastEoaToast) return;
    const t = window.setTimeout(() => setPastEoaToast(null), 2200);
    return () => window.clearTimeout(t);
  }, [pastEoaToast]);
  const [doneToast, setDoneToast] = useState<string | null>(null);
  useEffect(() => {
    if (!doneToast) return;
    const timeout = window.setTimeout(() => setDoneToast(null), 1600);
    return () => window.clearTimeout(timeout);
  }, [doneToast]);
  useEffect(() => {
    setDoneToast(null);
  }, [concept.key]);
  const handleMarkDone = useCallback(() => {
    if (isConfirmed) return;
    setConceptTag(speaker, concept.key, "confirmed");
    if (conceptInterval) {
      setConfirmedAnchor(speaker, concept.key, {
        start: conceptInterval.start,
        end: conceptInterval.end,
        matched_text: directOrthoInterval?.text || orthoInterval?.text || conceptInterval.text || undefined,
        source: "user+confirmed_tag",
        confirmed_at: new Date().toISOString(),
      });
      setDoneToast("Marked done.");
    } else {
      setDoneToast("Marked done. Time anchor skipped: no boundary.");
    }
  }, [concept.key, conceptInterval, directOrthoInterval, isConfirmed, orthoInterval, setConceptTag, setConfirmedAnchor, speaker]);

  const [ipa, setIpa] = useState(ipaInterval?.text ?? "");
  const [ortho, setOrtho] = useState(directOrthoInterval?.text || orthoInterval?.text || "");
  const [orthoUserEdited, setOrthoUserEdited] = useState(false);
  const [editStart, setEditStart] = useState<string>(conceptInterval ? conceptInterval.start.toFixed(3) : "");
  const [editEnd, setEditEnd] = useState<string>(conceptInterval ? conceptInterval.end.toFixed(3) : "");
  const [timestampSaving, setTimestampSaving] = useState(false);
  const [timestampMessage, setTimestampMessage] = useState<{ kind: "ok"; text: string } | { kind: "err"; text: string } | null>(null);
  const [userNote, setUserNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [quickRetimeMenu, setQuickRetimeMenu] = useState<{ x: number; y: number; start: number; end: number } | null>(null);

  useEffect(() => {
    setIpa(ipaInterval?.text ?? "");
    setOrtho(directOrthoInterval?.text || orthoInterval?.text || "");
    setOrthoUserEdited(false);
    setEditStart(conceptInterval ? conceptInterval.start.toFixed(3) : "");
    setEditEnd(conceptInterval ? conceptInterval.end.toFixed(3) : "");
    setTimestampMessage(null);
    setUserNote("");
    setNoteError(null);
    setSavingNote(false);
    setQuickRetimeMenu(null);
  }, [speaker, concept.key, conceptInterval, ipaInterval, orthoInterval, directOrthoInterval]);

  const [spectroOn, setSpectroOn] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [readyAudioUrl, setReadyAudioUrl] = useState("");
  const [zoom, setZoom] = useState(10);
  const [settingsAnchor, setSettingsAnchor] = useState<{ x: number; y: number } | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const spectroCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const spectroButtonRef = useRef<HTMLButtonElement | null>(null);

  const spectrogramParams = useSpectrogramSettings();
  const onSpectroContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    const rect = spectroButtonRef.current?.getBoundingClientRect();
    setSettingsAnchor({
      x: rect ? rect.right : event.clientX,
      y: rect ? rect.bottom + 6 : event.clientY,
    });
  }, []);

  const isPlaying = usePlaybackStore((s) => s.isPlaying);
  const currentTime = usePlaybackStore((s) => s.currentTime);
  const duration = usePlaybackStore((s) => s.duration);
  const selectedRegion = usePlaybackStore((s) => s.selectedRegion);
  const pendingSeek = usePlaybackStore((s) => s.pendingSeek);
  const volume = usePlaybackStore((s) => s.volume);
  const setStoreVolume = usePlaybackStore((s) => s.setVolume);
  const annotated = Boolean(conceptInterval && (ipaInterval || directOrthoInterval));
  const complete = Boolean(conceptInterval && ipaInterval && directOrthoInterval);

  const storedIntervalRef = useRef<{ start: number; end: number } | null>(null);
  useEffect(() => {
    storedIntervalRef.current = conceptInterval
      ? { start: conceptInterval.start, end: conceptInterval.end }
      : null;
  }, [conceptInterval]);

  const quickRetimeSelection = useMemo(() => (
    conceptInterval
      ? {
          enabled: true,
          label: `Update ${concept.name} timestamp`,
          onContextMenu: (selection: { start: number; end: number }, event: MouseEvent) => {
            event.preventDefault();
            setQuickRetimeMenu({ x: event.clientX, y: event.clientY, start: selection.start, end: selection.end });
          },
        }
      : null
  ), [concept.name, conceptInterval]);

  const {
    playPause,
    playRange,
    pause,
    seek,
    scrollToTimeAtFraction,
    skip,
    addRegion,
    clearQuickRetimeSelection,
    setZoom: wsSetZoom,
    setRate,
    setVolume: wsSetVolume,
    wsRef,
  } = useWaveSurfer({
    containerRef,
    audioUrl,
    peaksUrl,
    onTimeUpdate: (t) => usePlaybackStore.setState({ currentTime: t }),
    onReady: (d) => {
      usePlaybackStore.setState({ duration: d });
      setAudioReady(true);
      setReadyAudioUrl(audioUrl);
    },
    onPlayStateChange: (playing) => usePlaybackStore.setState({ isPlaying: playing }),
    onRegionUpdate: (start, end) => {
      usePlaybackStore.setState({ selectedRegion: { start, end } });
      setEditStart(start.toFixed(3));
      setEditEnd(end.toFixed(3));
    },
    onRegionCommit: (start, end) => {
      const previous = storedIntervalRef.current;
      if (!previous) return;
      if (Math.abs(previous.start - start) < 0.001 && Math.abs(previous.end - end) < 0.001) return;
      if (end <= start) return;
      const moved = moveIntervalAcrossTiers(speaker, previous.start, previous.end, start, end, LEXEME_SCOPE_TIERS);
      if (moved > 0) {
        storedIntervalRef.current = { start, end };
        setEditStart(start.toFixed(3));
        setEditEnd(end.toFixed(3));
        void saveSpeaker(speaker);
        setTimestampMessage({ kind: "ok", text: `Saved · ${moved} tier${moved === 1 ? "" : "s"}` });
      }
    },
    quickRetimeSelection,
  });

  // `orthoInterval` may be an auto-imported/display-only `ortho_words` fallback.
  // Do not persist that fallback as a direct ORTH annotation unless the user edits it.
  const saveOrthoText = (directOrthoInterval?.text || orthoUserEdited) ? ortho : "";

  const commitQuickRetime = useCallback(async () => {
    if (!conceptInterval || !quickRetimeMenu) return;
    setTimestampSaving(true);
    try {
      const result = saveLexemeAnnotation({
        speaker,
        oldStart: conceptInterval.start,
        oldEnd: conceptInterval.end,
        newStart: quickRetimeMenu.start,
        newEnd: quickRetimeMenu.end,
        ipaText: ipa,
        orthoText: saveOrthoText,
        conceptName: concept.name,
      });
      if (!result.ok) {
        setTimestampMessage({ kind: "err", text: result.error });
        return;
      }
      const saveResult = await saveSpeaker(speaker, record);
      const savedConceptInterval = saveResult?.record ? findAnnotationForConcept(saveResult.record, concept).conceptInterval : null;
      const savedStart = savedConceptInterval?.start ?? quickRetimeMenu.start;
      const savedEnd = savedConceptInterval?.end ?? quickRetimeMenu.end;
      const changedTierCount = saveResult?.changedTiers?.length ?? result.moved;
      storedIntervalRef.current = { start: savedStart, end: savedEnd };
      setEditStart(savedStart.toFixed(3));
      setEditEnd(savedEnd.toFixed(3));
      setTimestampMessage({ kind: "ok", text: `Saved (${changedTierCount} tier${changedTierCount === 1 ? "" : "s"} updated).` });
      clearQuickRetimeSelection();
      addRegion(savedStart, savedEnd);
      seek(savedStart);
      setQuickRetimeMenu(null);
    } catch (err) {
      setTimestampMessage({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setTimestampSaving(false);
    }
  }, [addRegion, clearQuickRetimeSelection, concept, conceptInterval, ipa, quickRetimeMenu, record, saveLexemeAnnotation, saveOrthoText, saveSpeaker, seek, speaker]);

  const cancelQuickRetime = useCallback(() => {
    clearQuickRetimeSelection();
    setQuickRetimeMenu(null);
  }, [clearQuickRetimeSelection]);

  const handleSaveNote = useCallback(async () => {
    setSavingNote(true);
    setNoteError(null);
    try {
      await saveLexemeNote({ speaker, concept_id: concept.key, user_note: userNote });
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingNote(false);
    }
  }, [concept.key, speaker, userNote]);

  useEffect(() => {
    if (!quickRetimeMenu) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      cancelQuickRetime();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cancelQuickRetime, quickRetimeMenu]);

  const handlePlayToggle = useCallback(() => {
    if (currentConceptPastEoa) {
      setPastEoaToast('Cannot seek past end of source audio.');
      return;
    }
    if (isPlaying) {
      pause();
      return;
    }
    if (selectedRegion) {
      playRange(selectedRegion.start, selectedRegion.end);
    } else {
      playPause();
    }
  }, [currentConceptPastEoa, isPlaying, selectedRegion, pause, playRange, playPause]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== " " && e.code !== "Space") return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable) return;
      }
      e.preventDefault();
      handlePlayToggle();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handlePlayToggle]);

  useEffect(() => {
    setAudioReady(false);
    setReadyAudioUrl("");
    usePlaybackStore.setState({
      currentTime: 0,
      duration: 0,
      isPlaying: false,
      selectedRegion: null,
    });
  }, [audioUrl]);

  useEffect(() => {
    if (!audioReady || readyAudioUrl !== audioUrl || !conceptInterval) return;
    wsSetZoom(400);
    setZoom(400);
    seek(conceptInterval.start);
    addRegion(conceptInterval.start, conceptInterval.end);
    scrollToTimeAtFraction(conceptInterval.start, 0.33);
  }, [audioReady, readyAudioUrl, audioUrl, conceptInterval?.start, conceptInterval?.end, seek, addRegion, wsSetZoom, scrollToTimeAtFraction]);

  // Mirror playbackRate pattern: apply persisted volume to the wavesurfer
  // instance once audio is ready, and re-apply on volume changes.
  useEffect(() => {
    if (!audioReady) return;
    wsSetVolume(volume);
  }, [audioReady, volume, wsSetVolume]);

  // Spectrogram time window — primary source: the waveform's currently visible
  // range (so the spectrogram aligns with what's drawn above and follows
  // playback as wavesurfer auto-scrolls). Throttled to 150 ms to keep worker
  // recompute frequency reasonable.
  const [waveformVisibleRange, setWaveformVisibleRange] =
    useState<{ startSec: number; endSec: number } | null>(null);

  useEffect(() => {
    const ws = wsRef.current;
    if (!ws || !audioReady) return;

    const THROTTLE_MS = 150;
    let lastUpdate = 0;
    let timeoutId: number | null = null;
    let pendingStart = 0;
    let pendingEnd = 0;

    const flush = () => {
      timeoutId = null;
      lastUpdate = Date.now();
      // Round to a 0.05 s grid so sub-pixel scroll noise doesn't churn React.
      const startSec = Math.max(0, Math.round(pendingStart * 20) / 20);
      const endSec = Math.max(startSec, Math.round(pendingEnd * 20) / 20);
      setWaveformVisibleRange((prev) => {
        if (prev && prev.startSec === startSec && prev.endSec === endSec) return prev;
        return { startSec, endSec };
      });
    };

    const handleScroll = (visibleStart: number, visibleEnd: number) => {
      pendingStart = visibleStart;
      pendingEnd = visibleEnd;
      const now = Date.now();
      if (now - lastUpdate >= THROTTLE_MS) {
        flush();
      } else if (timeoutId === null) {
        timeoutId = window.setTimeout(flush, THROTTLE_MS - (now - lastUpdate));
      }
    };

    // Seed from the DOM in case `scroll` hasn't fired yet (initial mount).
    type WaveSurferInternals = {
      options?: { minPxPerSec?: number };
      getWrapper?: () => HTMLElement | null | undefined;
    };
    const internals = ws as unknown as WaveSurferInternals;
    const minPxPerSec = internals.options?.minPxPerSec;
    const wrapper = internals.getWrapper?.();
    if (wrapper && typeof minPxPerSec === "number" && minPxPerSec > 0) {
      pendingStart = wrapper.scrollLeft / minPxPerSec;
      pendingEnd = (wrapper.scrollLeft + wrapper.clientWidth) / minPxPerSec;
      flush();
    }

    // wavesurfer v7's `on()` returns an unsubscribe; some mocks (and older
    // wavesurfer builds) don't, so fall back to `un()`.
    const off = ws.on("scroll", handleScroll);
    return () => {
      if (typeof off === "function") {
        off();
      } else {
        (ws as unknown as { un: typeof ws.on }).un?.("scroll", handleScroll);
      }
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
  }, [audioReady, wsRef]);

  // Concept-based fallback (used briefly until `scroll` fires, or in tests
  // where there's no real wavesurfer instance).
  const conceptTimeRange = useMemo(() => {
    if (!conceptInterval) return undefined;
    const padding = 0.5;
    const start = Math.max(0, conceptInterval.start - padding);
    const end = duration > 0
      ? Math.min(duration, conceptInterval.end + padding)
      : conceptInterval.end + padding;
    return { startSec: start, endSec: end };
  }, [conceptInterval, duration]);

  // Cascade: prefer the live waveform window, fall back to concept ± padding,
  // finally fall back to the first 30 s of audio (mirrors the hook's default).
  const effectiveSpectrogramRange = useMemo(() => {
    if (waveformVisibleRange) return waveformVisibleRange;
    if (conceptTimeRange) return conceptTimeRange;
    if (duration <= 0) return null;
    return { startSec: 0, endSec: Math.min(duration, 30) };
  }, [waveformVisibleRange, conceptTimeRange, duration]);

  const spectrogramPlayheadPercent = useMemo(() => {
    if (!effectiveSpectrogramRange) return null;
    const { startSec, endSec } = effectiveSpectrogramRange;
    const sliceLen = endSec - startSec;
    if (sliceLen <= 0) return null;
    if (currentTime < startSec || currentTime > endSec) return null;
    return ((currentTime - startSec) / sliceLen) * 100;
  }, [effectiveSpectrogramRange, currentTime]);

  useSpectrogram({
    enabled: spectroOn && audioReady,
    wsRef,
    canvasRef: spectroCanvasRef,
    params: {
      windowLengthSec: spectrogramParams.windowLengthSec,
      windowShape: spectrogramParams.windowShape,
      maxFrequencyHz: spectrogramParams.maxFrequencyHz,
      dynamicRangeDb: spectrogramParams.dynamicRangeDb,
      preEmphasisHz: spectrogramParams.preEmphasisHz,
      colorScheme: spectrogramParams.colorScheme,
    },
    timeRange: waveformVisibleRange ?? conceptTimeRange,
  });

  useEffect(() => {
    if (!pendingSeek) return;
    if (!audioReady || readyAudioUrl !== audioUrl) return;
    seek(pendingSeek.targetSec);
    scrollToTimeAtFraction(pendingSeek.targetSec, 0.33);
  }, [pendingSeek?.nonce, audioReady, readyAudioUrl, audioUrl, seek, scrollToTimeAtFraction]);

  const fmt = formatPlaybackTime;

  return (
    <main className="flex-1 overflow-y-auto bg-slate-50">
      <section className="border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-2.5">
          <div className="flex items-center gap-1">
            <button
              title="Previous segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const previous = intervals
                  .filter((interval) => interval.end < currentTime - 0.1)
                  .sort((a, b) => b.end - a.end)[0];
                if (previous) {
                  skip(-(currentTime - previous.start));
                } else {
                  skip(-currentTime);
                }
              }}
            >
              <SkipBack className="h-3.5 w-3.5" />
            </button>
            <button
              title="Next segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const next = intervals
                  .filter((interval) => interval.start > currentTime + 0.1)
                  .sort((a, b) => a.start - b.start)[0];
                if (next) {
                  skip(next.start - currentTime);
                }
              }}
            >
              <SkipForward className="h-3.5 w-3.5" />
            </button>
            <div className="mx-2 h-5 w-px bg-slate-200" />
            <button
              onClick={() => {
                const nextZoom = Math.max(10, zoom - 20);
                setZoom(nextZoom);
                wsSetZoom(nextZoom);
              }}
              title="Zoom out"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <div className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500">{zoom}px/s</div>
            <button
              onClick={() => {
                const nextZoom = Math.min(500, zoom + 20);
                setZoom(nextZoom);
                wsSetZoom(nextZoom);
              }}
              title="Zoom in"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              ref={spectroButtonRef}
              onClick={() => setSpectroOn((value) => !value)}
              onContextMenu={onSpectroContextMenu}
              title="Toggle spectrogram (right-click for settings)"
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-semibold transition ${spectroOn ? "bg-indigo-600 text-white" : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"}`}
            >
              <Activity className="h-3 w-3" /> Spectrogram
            </button>
          </div>
        </div>

        <div className="relative px-5 pt-4 pb-2">
          <div className="relative" style={{ paddingLeft: LABEL_COL_PX }}>
            <div
              ref={containerRef}
              className="relative w-full overflow-hidden rounded-lg ring-1 ring-slate-100"
              style={{ minHeight: 110 }}
            >
              <span
                aria-label="Waveform playhead time"
                title="Current playhead time"
                className="pointer-events-none absolute right-2 top-2 z-10 rounded-md border border-slate-200 bg-white/90 px-2 py-1 font-mono text-[11px] font-semibold tabular-nums text-slate-700 shadow-sm"
              >
                {formatPlayhead(currentTime)}
              </span>
            </div>
            {spectroOn && (
              <div
                data-testid="spectrogram-row"
                className="relative mt-1 overflow-hidden rounded-lg ring-1 ring-slate-100 bg-white"
                style={{ height: SPEC_HEIGHT }}
              >
                <canvas
                  ref={spectroCanvasRef}
                  className="block h-full w-full"
                />
                {spectrogramPlayheadPercent !== null && (
                  <div
                    data-testid="spectrogram-playhead"
                    aria-hidden="true"
                    className="pointer-events-none absolute top-0 bottom-0 w-px bg-indigo-500"
                    style={{ left: `${spectrogramPlayheadPercent}%` }}
                  />
                )}
              </div>
            )}
            {quickRetimeMenu && (
              <div
                role="menu"
                aria-label="Waveform quick retime menu"
                className="fixed z-50 min-w-52 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
                style={{ left: quickRetimeMenu.x, top: quickRetimeMenu.y }}
                onContextMenu={(event) => event.preventDefault()}
              >
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full px-3 py-2 text-left text-slate-700 hover:bg-slate-50"
                  onClick={() => void commitQuickRetime()}
                >
                  Update {concept.name} timestamp
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full border-t border-slate-100 px-3 py-2 text-left text-slate-600 hover:bg-slate-50"
                  onClick={cancelQuickRetime}
                >
                  Cancel selection
                </button>
              </div>
            )}
          </div>
        </div>

        <TranscriptionLanes speaker={speaker} wsRef={wsRef} audioReady={audioReady} onSeek={seek} />
      </section>

      <SpeakerHeader
        annotated={annotated}
        complete={complete}
        concept={concept}
        speaker={speaker}
        totalConcepts={totalConcepts}
        onPrev={onPrev}
        onNext={onNext}
      />

      {pastEoaSummary.pastEoa > 0 && typeof sourceAudioDurationSec === 'number' ? (
        <section className="px-8 pt-3" data-testid="past-eoa-banner">
          <div className="mx-auto max-w-4xl rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            <strong className="font-semibold">{pastEoaSummary.pastEoa}</strong>
            {" of "}
            <strong className="font-semibold">{pastEoaSummary.total}</strong>
            {" concept rows are past the end of the source audio ("}
            <span className="font-mono">{formatDurationHuman(sourceAudioDurationSec)}</span>
            {") and cannot be played until the working WAV is extended. Editing text fields is still permitted."}
          </div>
        </section>
      ) : null}

      {pastEoaToast ? (
        <section className="px-8 pt-2" data-testid="past-eoa-toast">
          <div className="mx-auto max-w-4xl rounded-md border border-slate-200 bg-slate-100 px-3 py-1.5 text-[11px] text-slate-700">
            {pastEoaToast}
          </div>
        </section>
      ) : null}

      <section className="px-8 py-6">
        <div className="mx-auto max-w-4xl space-y-5">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">IPA Transcription</label>
            <input
              value={ipa}
              onChange={(e) => setIpa(e.target.value)}
              placeholder="Enter IPA…"
              dir="ltr"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-lg text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Orthographic</label>
            <input
              value={ortho}
              onChange={(e) => {
                setOrthoUserEdited(true);
                setOrtho(e.target.value);
              }}
              placeholder="Enter orthographic form…"
              dir="rtl"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-serif text-xl text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Speaker Notes</label>
            <textarea
              data-testid={`lexeme-user-note-${speaker}-${concept.key}`}
              value={userNote}
              onChange={(e) => setUserNote(e.target.value)}
              onBlur={() => void handleSaveNote()}
              placeholder="Add notes specific to this speaker/lexeme…"
              className="mt-2 min-h-[72px] w-full resize-y rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-300 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
            <div className={`mt-1 text-[10px] ${savingNote ? "text-slate-500" : noteError ? "text-rose-600" : "text-transparent"}`}>
              {savingNote ? "Saving…" : noteError ?? "saved"}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Lexeme timestamp (seconds)</label>
              {conceptInterval ? (
                <span className="font-mono text-[10px] text-slate-400">{fmt(conceptInterval.start)}–{fmt(conceptInterval.end)}</span>
              ) : (
                <span className="font-mono text-[10px] text-slate-400">no interval</span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-medium text-slate-500">Start</span>
                <input
                  data-testid="lexeme-start"
                  type="number"
                  step={0.001}
                  min={0}
                  value={editStart}
                  onChange={(e) => setEditStart(e.target.value)}
                  disabled={!conceptInterval}
                  className="w-28 rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1 font-mono text-xs text-slate-800 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-medium text-slate-500">End</span>
                <input
                  data-testid="lexeme-end"
                  type="number"
                  step={0.001}
                  min={0}
                  value={editEnd}
                  onChange={(e) => setEditEnd(e.target.value)}
                  disabled={!conceptInterval}
                  className="w-28 rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1 font-mono text-xs text-slate-800 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
                />
              </div>
              <button
                type="button"
                data-testid="confirm-time"
                disabled={!conceptInterval}
                aria-pressed={Boolean(confirmedAnchor)}
                title="Confirms the lexeme boundaries without requiring transcription. Used by cross-speaker anchor discovery in lexeme_search Signal B, audio re-STT priors, forced-alignment training data, and future audio-similarity discovery."
                onClick={() => {
                  if (!conceptInterval) return;
                  if (confirmedAnchor) {
                    setConfirmedAnchor(speaker, concept.key, null);
                    setTimestampMessage({ kind: "ok", text: "Boundary confirmation cleared." });
                    return;
                  }
                  const nextStart = parseFloat(editStart);
                  const nextEnd = parseFloat(editEnd);
                  const start = Number.isFinite(nextStart) ? nextStart : conceptInterval.start;
                  const end = Number.isFinite(nextEnd) ? nextEnd : conceptInterval.end;
                  setConfirmedAnchor(speaker, concept.key, {
                    start,
                    end,
                    source: "user+boundary_only",
                    confirmed_at: new Date().toISOString(),
                  });
                  setTimestampMessage({ kind: "ok", text: "Boundary confirmed." });
                }}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${confirmedAnchor ? "bg-emerald-600 text-white" : "border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50"}`}
              >
                <Check className="h-3.5 w-3.5" /> Confirm time
              </button>
              {timestampMessage && (
                <span data-testid="lexeme-timestamp-msg" className={`ml-auto text-[11px] ${timestampMessage.kind === "ok" ? "text-emerald-600" : "text-rose-600"}`}>
                  {timestampMessage.text}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              data-testid="save-lexeme-annotation"
              disabled={!conceptInterval || timestampSaving}
              onClick={async () => {
                if (!conceptInterval) return;
                const nextStart = parseFloat(editStart);
                const nextEnd = parseFloat(editEnd);
                setTimestampSaving(true);
                try {
                  const result = saveLexemeAnnotation({
                    speaker,
                    oldStart: conceptInterval.start,
                    oldEnd: conceptInterval.end,
                    newStart: nextStart,
                    newEnd: nextEnd,
                    ipaText: ipa,
                    orthoText: saveOrthoText,
                    conceptName: concept.name,
                  });
                  if (!result.ok) {
                    setTimestampMessage({ kind: "err", text: result.error });
                  } else {
                    const saveResult = await saveSpeaker(speaker, record);
                    const savedConceptInterval = saveResult?.record ? findAnnotationForConcept(saveResult.record, concept).conceptInterval : null;
                    const savedStart = savedConceptInterval?.start ?? nextStart;
                    const savedEnd = savedConceptInterval?.end ?? nextEnd;
                    const changedTierCount = saveResult?.changedTiers?.length ?? result.moved;
                    storedIntervalRef.current = { start: savedStart, end: savedEnd };
                    setEditStart(savedStart.toFixed(3));
                    setEditEnd(savedEnd.toFixed(3));
                    setTimestampMessage({ kind: "ok", text: `Saved (${changedTierCount} tier${changedTierCount === 1 ? "" : "s"} updated).` });
                    addRegion(savedStart, savedEnd);
                    seek(savedStart);
                  }
                } catch (err) {
                  setTimestampMessage({ kind: "err", text: err instanceof Error ? err.message : String(err) });
                } finally {
                  setTimestampSaving(false);
                }
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              <Save className="h-4 w-4" /> Save Annotation
            </button>
            <div className="relative">
              <button
                type="button"
                data-testid="annotate-mark-done"
                aria-pressed={isConfirmed}
                onClick={handleMarkDone}
                className={`inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold shadow-sm transition ${
                  isConfirmed
                    ? "bg-emerald-700 text-white hover:bg-emerald-700"
                    : "border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50"
                }`}
              >
                <Check className="h-4 w-4" /> {isConfirmed ? "Confirmed" : "Mark Done"}
              </button>
              {doneToast && (
                <div
                  role="status"
                  data-testid="annotate-mark-done-toast"
                  className="absolute bottom-full left-0 mb-1.5 whitespace-nowrap rounded-md border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700 shadow-md"
                >
                  {doneToast}
                </div>
              )}
            </div>
            {onCaptureOffsetAnchor && (
              <div className="relative">
                <button
                  onClick={onCaptureOffsetAnchor}
                  data-testid="annotate-capture-anchor"
                  title="Anchor offset detection to this lexeme + the current playback time. Locks this lexeme against future global offset passes."
                  className="inline-flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm font-semibold text-indigo-700 transition hover:bg-indigo-100"
                >
                  <Anchor className="h-4 w-4" /> Anchor offset here
                </button>
                {captureToast && (
                  <div
                    role="status"
                    data-testid="annotate-capture-toast"
                    className="absolute bottom-full left-0 mb-1.5 whitespace-nowrap rounded-md border border-emerald-200 bg-white px-2.5 py-1 text-[11px] text-emerald-700 shadow-md"
                  >
                    {captureToast}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="sticky bottom-0 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-8 py-3">
          <button onClick={() => skip(-5)} title="-5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipBack className="h-4 w-4" /></button>
          <button onClick={() => skip(-1)} title="-1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronLeft className="h-4 w-4" /></button>
          <button
            onClick={handlePlayToggle}
            aria-disabled={currentConceptPastEoa || undefined}
            title={
              currentConceptPastEoa
                ? `This concept's interval starts past the end of the source audio (${typeof sourceAudioDurationSec === 'number' ? sourceAudioDurationSec.toFixed(1) : '?'}s). Audio cannot play yet.`
                : selectedRegion ? "Play selected region (Space)" : "Play (Space)"
            }
            data-testid="annotate-play"
            className={
              "grid h-10 w-10 place-items-center rounded-full text-white shadow-sm " +
              (currentConceptPastEoa
                ? "bg-slate-300 cursor-not-allowed"
                : "bg-slate-900 hover:bg-slate-700")
            }
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 translate-x-[1px]" />}
          </button>
          <button onClick={() => skip(1)} title="+1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronRight className="h-4 w-4" /></button>
          <button onClick={() => skip(5)} title="+5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipForward className="h-4 w-4" /></button>

          <div className="ml-2 font-mono text-[11px] tabular-nums text-slate-500">
            {fmt(currentTime)} <span className="text-slate-300">/</span> {fmt(duration)}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600" title={`Volume: ${Math.round(volume * 100)}%`}>
              <span className="text-slate-500">Vol</span>
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(volume * 100)}
                onChange={(e) => setStoreVolume(Number(e.target.value) / 100)}
                aria-label="Volume"
                data-testid="annotate-volume"
                className="h-1 w-20 cursor-pointer accent-slate-700"
              />
            </label>
            <select defaultValue="1" onChange={(e) => setRate(Number(e.target.value))} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 focus:border-indigo-300 focus:outline-none">
              <option value="0.5">0.5x</option>
              <option value="0.75">0.75x</option>
              <option value="1">1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2.0x</option>
            </select>
            <button
              onClick={handleUndo}
              disabled={!canUndo}
              data-testid="annotate-undo"
              title={canUndo ? `Undo ${nextUndoLabel} (⌘Z)` : "Nothing to undo"}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Undo2 className="h-3 w-3" /> Undo
            </button>
            <button
              onClick={handleRedo}
              disabled={!canRedo}
              data-testid="annotate-redo"
              title={canRedo ? `Redo ${nextRedoLabel} (⇧⌘Z)` : "Nothing to redo"}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Redo2 className="h-3 w-3" /> Redo
            </button>
          </div>
        </div>
        {undoToast && (
          <div
            role="status"
            data-testid="annotate-undo-toast"
            className="pointer-events-none absolute bottom-14 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-indigo-200 bg-white px-3 py-1 text-[11px] text-indigo-700 shadow-md"
          >
            {undoToast}
          </div>
        )}
      </section>
      {settingsAnchor && (
        <SpectrogramSettings
          anchor={settingsAnchor}
          onClose={() => setSettingsAnchor(null)}
        />
      )}
    </main>
  );
};
