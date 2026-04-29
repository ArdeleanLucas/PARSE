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
import { useTagStore } from "../../../stores/tagStore";
import { saveLexemeNote } from "../../../api/client";
import { LABEL_COL_PX, TranscriptionLanes } from "../TranscriptionLanes";

import { SpeakerHeader } from "./SpeakerHeader";
import { findAnnotationForConcept, formatPlaybackTime, formatPlayhead, pickOrthoIntervalForConcept } from "./shared";
import type { AnnotateViewProps } from "./types";

export { pickOrthoIntervalForConcept };

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

  const tagConcept = useTagStore((s) => s.tagConcept);

  const { conceptInterval, ipaInterval, orthoInterval } = useMemo(
    () => findAnnotationForConcept(record, concept),
    [record, concept],
  );
  const [ipa, setIpa] = useState(ipaInterval?.text ?? "");
  const [ortho, setOrtho] = useState(orthoInterval?.text ?? "");
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
    setOrtho(orthoInterval?.text ?? "");
    setEditStart(conceptInterval ? conceptInterval.start.toFixed(3) : "");
    setEditEnd(conceptInterval ? conceptInterval.end.toFixed(3) : "");
    setTimestampMessage(null);
    setUserNote("");
    setNoteError(null);
    setSavingNote(false);
    setQuickRetimeMenu(null);
  }, [speaker, concept.key, conceptInterval, ipaInterval, orthoInterval]);

  const [spectroOn, setSpectroOn] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [readyAudioUrl, setReadyAudioUrl] = useState("");
  const [zoom, setZoom] = useState(10);

  const containerRef = useRef<HTMLDivElement>(null);
  const spectroCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const isPlaying = usePlaybackStore((s) => s.isPlaying);
  const currentTime = usePlaybackStore((s) => s.currentTime);
  const duration = usePlaybackStore((s) => s.duration);
  const selectedRegion = usePlaybackStore((s) => s.selectedRegion);
  const pendingSeek = usePlaybackStore((s) => s.pendingSeek);
  const volume = usePlaybackStore((s) => s.volume);
  const setStoreVolume = usePlaybackStore((s) => s.setVolume);
  const annotated = Boolean(conceptInterval && ipaInterval);

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
        orthoText: ortho,
        conceptName: concept.name,
      });
      if (!result.ok) {
        setTimestampMessage({ kind: "err", text: result.error });
        return;
      }
      await saveSpeaker(speaker);
      storedIntervalRef.current = { start: quickRetimeMenu.start, end: quickRetimeMenu.end };
      setEditStart(quickRetimeMenu.start.toFixed(3));
      setEditEnd(quickRetimeMenu.end.toFixed(3));
      setTimestampMessage({ kind: "ok", text: `Saved (${result.moved} tier${result.moved === 1 ? "" : "s"} updated).` });
      clearQuickRetimeSelection();
      addRegion(quickRetimeMenu.start, quickRetimeMenu.end);
      seek(quickRetimeMenu.start);
      setQuickRetimeMenu(null);
    } catch (err) {
      setTimestampMessage({ kind: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setTimestampSaving(false);
    }
  }, [addRegion, clearQuickRetimeSelection, concept.name, conceptInterval, ipa, ortho, quickRetimeMenu, saveLexemeAnnotation, saveSpeaker, seek, speaker]);

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
    if (isPlaying) {
      pause();
      return;
    }
    if (selectedRegion) {
      playRange(selectedRegion.start, selectedRegion.end);
    } else {
      playPause();
    }
  }, [isPlaying, selectedRegion, pause, playRange, playPause]);

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

  useSpectrogram({ enabled: spectroOn && audioReady, wsRef, canvasRef: spectroCanvasRef });

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
              onClick={() => setSpectroOn((value) => !value)}
              title="Toggle spectrogram"
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
              <canvas
                ref={spectroCanvasRef}
                className="pointer-events-none absolute inset-y-0 right-0 rounded-lg"
                style={{ left: LABEL_COL_PX, opacity: 0.6, mixBlendMode: "multiply" }}
              />
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
        concept={concept}
        speaker={speaker}
        totalConcepts={totalConcepts}
        onPrev={onPrev}
        onNext={onNext}
      />

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
              onChange={(e) => setOrtho(e.target.value)}
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
                    orthoText: ortho,
                    conceptName: concept.name,
                  });
                  if (!result.ok) {
                    setTimestampMessage({ kind: "err", text: result.error });
                  } else {
                    await saveSpeaker(speaker);
                    storedIntervalRef.current = { start: nextStart, end: nextEnd };
                    setEditStart(nextStart.toFixed(3));
                    setEditEnd(nextEnd.toFixed(3));
                    setTimestampMessage({ kind: "ok", text: `Saved (${result.moved} tier${result.moved === 1 ? "" : "s"} updated).` });
                    addRegion(nextStart, nextEnd);
                    seek(nextStart);
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
            <button
              onClick={() => tagConcept("confirmed", concept.key)}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-semibold text-rose-600 transition hover:bg-rose-50"
            >
              <Check className="h-4 w-4" /> Mark Done
            </button>
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
            title={selectedRegion ? "Play selected region (Space)" : "Play (Space)"}
            data-testid="annotate-play"
            className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white shadow-sm hover:bg-slate-700"
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
    </main>
  );
};
