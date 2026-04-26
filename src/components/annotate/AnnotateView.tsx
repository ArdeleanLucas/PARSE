import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Anchor,
  Check,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  Pause,
  Play,
  Redo2,
  Save,
  SkipBack,
  SkipForward,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import type { AnnotationInterval, AnnotationRecord } from '../../api/types';
import { useSpectrogram } from '../../hooks/useSpectrogram';
import { useWaveSurfer } from '../../hooks/useWaveSurfer';
import { useAnnotationStore } from '../../stores/annotationStore';
import { usePlaybackStore } from '../../stores/playbackStore';
import { useTagStore } from '../../stores/tagStore';
import { TranscriptionLanes, LABEL_COL_PX } from './TranscriptionLanes';

interface Concept {
  id: number | string;
  key: string;
  name: string;
}

function formatPlaybackTime(t: number): string {
  if (!Number.isFinite(t) || t < 0) return '00:00.00';
  const m = Math.floor(t / 60).toString().padStart(2, '0');
  const s = Math.floor(t % 60).toString().padStart(2, '0');
  const ms = Math.floor((t * 100) % 100).toString().padStart(2, '0');
  return `${m}:${s}.${ms}`;
}

function overlaps(a: AnnotationInterval, b: AnnotationInterval): boolean {
  return a.start <= b.end && b.start <= a.end;
}

function conceptMatchesIntervalText(concept: { name: string; key: string }, text: string): boolean {
  const normalizedText = text.trim().toLowerCase();
  const normalizedName = concept.name.trim().toLowerCase();
  const normalizedKey = concept.key.trim().toLowerCase();

  return normalizedText === normalizedName
    || normalizedText === normalizedKey
    || normalizedText.includes(normalizedName);
}

// Prefer word-level ortho_words (from Tier-2 forced alignment) over the
// coarse ortho tier. When the coarse tier is one monolithic segment — as
// razhan often produces on long elicited word-list recordings — picking
// the whole-paragraph interval by overlap dumps the entire narrative into
// a single lexeme field. The word-level tier yields a single clean word.
export function pickOrthoIntervalForConcept(
  record: AnnotationRecord,
  conceptInterval: AnnotationInterval,
): AnnotationInterval | null {
  const words = record.tiers.ortho_words?.intervals ?? [];
  if (words.length) {
    const contained = words.find(
      (iv) => iv.start >= conceptInterval.start && iv.end <= conceptInterval.end,
    );
    if (contained) return contained;

    let bestOverlap = 0;
    let bestWord: AnnotationInterval | null = null;
    for (const iv of words) {
      if (iv.end <= conceptInterval.start || iv.start >= conceptInterval.end) continue;
      const ov = Math.min(iv.end, conceptInterval.end) - Math.max(iv.start, conceptInterval.start);
      if (ov > bestOverlap) {
        bestOverlap = ov;
        bestWord = iv;
      }
    }
    if (bestWord) return bestWord;
  }
  return (record.tiers.ortho?.intervals ?? []).find((iv) => overlaps(iv, conceptInterval)) ?? null;
}

function findAnnotationForConcept(record: AnnotationRecord | null | undefined, concept: Concept) {
  if (!record) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const conceptIntervals = record.tiers.concept?.intervals ?? [];
  const conceptInterval = conceptIntervals.find((interval) => conceptMatchesIntervalText(concept, interval.text)) ?? null;

  if (!conceptInterval) {
    return { conceptInterval: null, ipaInterval: null, orthoInterval: null };
  }

  const ipaInterval = (record.tiers.ipa?.intervals ?? []).find((interval) => overlaps(interval, conceptInterval)) ?? null;
  const orthoInterval = pickOrthoIntervalForConcept(record, conceptInterval);

  return { conceptInterval, ipaInterval, orthoInterval };
}

export interface AnnotateViewProps {
  concept: Concept;
  speaker: string;
  totalConcepts: number;
  onPrev: () => void;
  onNext: () => void;
  audioUrl: string;
  peaksUrl?: string;
  onCaptureOffsetAnchor?: () => void;
  captureToast?: string | null;
}

export const AnnotateView: React.FC<AnnotateViewProps> = ({ concept, speaker, totalConcepts, onPrev, onNext, audioUrl, peaksUrl, onCaptureOffsetAnchor, captureToast }) => {
  const record = useAnnotationStore(s => s.records[speaker] ?? null);
  const setInterval = useAnnotationStore(s => s.setInterval);
  const moveIntervalAcrossTiers = useAnnotationStore(s => s.moveIntervalAcrossTiers);
  const saveSpeaker = useAnnotationStore(s => s.saveSpeaker);
  const undoAnnotation = useAnnotationStore(s => s.undo);
  const redoAnnotation = useAnnotationStore(s => s.redo);
  const undoRedoHistory = useAnnotationStore(s => s.histories[speaker] ?? null);
  const canUndo = (undoRedoHistory?.undo.length ?? 0) > 0;
  const canRedo = (undoRedoHistory?.redo.length ?? 0) > 0;
  const nextUndoLabel = canUndo ? undoRedoHistory!.undo[undoRedoHistory!.undo.length - 1].label : '';
  const nextRedoLabel = canRedo ? undoRedoHistory!.redo[undoRedoHistory!.redo.length - 1].label : '';
  const [undoToast, setUndoToast] = useState<string | null>(null);
  useEffect(() => {
    if (!undoToast) return;
    const t = window.setTimeout(() => setUndoToast(null), 2200);
    return () => window.clearTimeout(t);
  }, [undoToast]);
  const handleUndo = useCallback(() => {
    const label = undoAnnotation(speaker);
    if (label) setUndoToast(`Undid ${label}`);
  }, [speaker, undoAnnotation]);
  const handleRedo = useCallback(() => {
    const label = redoAnnotation(speaker);
    if (label) setUndoToast(`Redid ${label}`);
  }, [speaker, redoAnnotation]);
  // Ctrl/Cmd+Z = undo, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y = redo. Suppressed while
  // the user is typing in inputs, textareas, selects, or a contenteditable
  // element (the inline lane editor) so their keystrokes don't get hijacked.
  useEffect(() => {
    if (!speaker) return;
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (target.isContentEditable) return;
      }
      const key = e.key.toLowerCase();
      if (key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((key === 'z' && e.shiftKey) || key === 'y') {
        e.preventDefault();
        handleRedo();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [speaker, handleUndo, handleRedo]);
  const tagConcept = useTagStore(s => s.tagConcept);

  const { conceptInterval, ipaInterval, orthoInterval } = useMemo(
    () => findAnnotationForConcept(record, concept),
    [record, concept]
  );
  const [ipa, setIpa] = useState(ipaInterval?.text ?? '');
  const [ortho, setOrtho] = useState(orthoInterval?.text ?? '');
  // Editable timestamp fields for the current lexeme (seeded from the concept tier interval).
  const [editStart, setEditStart] = useState<string>(conceptInterval ? conceptInterval.start.toFixed(3) : '');
  const [editEnd, setEditEnd] = useState<string>(conceptInterval ? conceptInterval.end.toFixed(3) : '');
  const [timestampSaving, setTimestampSaving] = useState(false);
  const [timestampMessage, setTimestampMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  useEffect(() => {
    setIpa(ipaInterval?.text ?? '');
    setOrtho(orthoInterval?.text ?? '');
    setEditStart(conceptInterval ? conceptInterval.start.toFixed(3) : '');
    setEditEnd(conceptInterval ? conceptInterval.end.toFixed(3) : '');
    setTimestampMessage(null);
  }, [speaker, concept.key, conceptInterval, ipaInterval, orthoInterval]);

  const [spectroOn, setSpectroOn] = useState(false);
  const [audioReady, setAudioReady] = useState(false);
  const [readyAudioUrl, setReadyAudioUrl] = useState('');
  const [zoom, setZoom] = useState(10); // minPxPerSec

  const containerRef = useRef<HTMLDivElement>(null);
  const spectroCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const isPlaying = usePlaybackStore(s => s.isPlaying);
  const currentTime = usePlaybackStore(s => s.currentTime);
  const duration = usePlaybackStore(s => s.duration);
  const selectedRegion = usePlaybackStore(s => s.selectedRegion);
  const annotated = Boolean(conceptInterval && ipaInterval);

  // Ref mirror of the currently stored concept interval. Used from the
  // onRegionCommit closure (which is captured on WaveSurfer init) so it
  // always sees the latest stored start/end when the user releases a drag.
  const storedIntervalRef = useRef<{ start: number; end: number } | null>(null);
  useEffect(() => {
    storedIntervalRef.current = conceptInterval
      ? { start: conceptInterval.start, end: conceptInterval.end }
      : null;
  }, [conceptInterval]);

  const { playPause, playRange, pause, seek, scrollToTimeAtFraction, skip, addRegion, setZoom: wsSetZoom, setRate, wsRef } = useWaveSurfer({
    containerRef,
    audioUrl,
    peaksUrl,
    onTimeUpdate: t => usePlaybackStore.setState({ currentTime: t }),
    onReady: d => {
      usePlaybackStore.setState({ duration: d });
      setAudioReady(true);
      setReadyAudioUrl(audioUrl);
    },
    onPlayStateChange: p => usePlaybackStore.setState({ isPlaying: p }),
    onRegionUpdate: (start, end) => {
      usePlaybackStore.setState({ selectedRegion: { start, end } });
      // Dragging/resizing the waveform region mirrors into the editable fields.
      setEditStart(start.toFixed(3));
      setEditEnd(end.toFixed(3));
    },
    onRegionCommit: (start, end) => {
      // Auto-save: when the user finishes dragging/resizing the region,
      // retime the current lexeme across all tiers and persist to the
      // annotation JSON. No Save button needed for region edits.
      const prev = storedIntervalRef.current;
      if (!prev) return;
      if (Math.abs(prev.start - start) < 0.001 && Math.abs(prev.end - end) < 0.001) return;
      if (end <= start) return;
      const moved = moveIntervalAcrossTiers(speaker, prev.start, prev.end, start, end);
      if (moved > 0) {
        storedIntervalRef.current = { start, end };
        setEditStart(start.toFixed(3));
        setEditEnd(end.toFixed(3));
        void saveSpeaker(speaker);
        setTimestampMessage({ kind: 'ok', text: `Saved · ${moved} tier${moved === 1 ? '' : 's'}` });
      }
    },
  });

  // Press Play (or Space) on a selected region → clip-bounded playback that
  // stops at the region end. No region selected → plain play/pause toggle.
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

  // Global Space hotkey for play/pause. Skips when the user is typing so the
  // IPA and orthographic fields keep accepting spaces.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== " " && e.code !== "Space") return;
      const t = e.target as HTMLElement | null;
      if (t) {
        const tag = t.tagName?.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select" || t.isContentEditable) return;
      }
      e.preventDefault();
      handlePlayToggle();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handlePlayToggle]);

  // Speaker switches replace the underlying WaveSurfer instance. Reset the
  // ready gate and playback clock first so annotate-side seek/region effects
  // wait for the new audio file instead of operating on a half-torn-down
  // instance from the previous speaker.
  useEffect(() => {
    setAudioReady(false);
    setReadyAudioUrl('');
    usePlaybackStore.setState({
      currentTime: 0,
      duration: 0,
      isPlaying: false,
      selectedRegion: null,
    });
  }, [audioUrl]);

  // When the user picks a concept (and once the waveform is ready): zoom
  // in to 400 px/s, seek to its start, draw the lexeme range as a draggable
  // region, and scroll so the start sits at ~33% from the left of the
  // viewport (leaves more of the trailing audio visible than centering).
  useEffect(() => {
    if (!audioReady || readyAudioUrl !== audioUrl || !conceptInterval) return;
    wsSetZoom(400);
    setZoom(400);
    seek(conceptInterval.start);
    addRegion(conceptInterval.start, conceptInterval.end);
    scrollToTimeAtFraction(conceptInterval.start, 0.33);
  }, [audioReady, readyAudioUrl, audioUrl, conceptInterval?.start, conceptInterval?.end, seek, addRegion, wsSetZoom, scrollToTimeAtFraction]);

  useSpectrogram({ enabled: spectroOn && audioReady, wsRef, canvasRef: spectroCanvasRef });

  // Cross-component seek bridge — the right-panel "Search & anchor" block
  // calls usePlaybackStore.requestSeek(targetSec); we watch the nonce and
  // drive our local wavesurfer seek.
  const pendingSeek = usePlaybackStore(s => s.pendingSeek);
  useEffect(() => {
    if (!pendingSeek) return;
    if (!audioReady || readyAudioUrl !== audioUrl) return;
    seek(pendingSeek.targetSec);
    scrollToTimeAtFraction(pendingSeek.targetSec, 0.33);
  }, [pendingSeek?.nonce, audioReady, readyAudioUrl, audioUrl, seek, scrollToTimeAtFraction]);

  // fmt now lives at module scope (formatPlaybackTime) — kept as a local
  // alias so the inline JSX below stays diff-friendly with prior versions.
  const fmt = formatPlaybackTime;

  return (
    <main className="flex-1 overflow-y-auto bg-slate-50">
      {/* ======= WAVEFORM / VIRTUAL TIMELINE ======= */}
      <section className="border-b border-slate-200 bg-white">
        {/* Toolbar */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-2.5">
          <div className="flex items-center gap-1">
            <button
              title="Previous segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const prev = intervals
                  .filter(iv => iv.end < currentTime - 0.1)
                  .sort((a, b) => b.end - a.end)[0];
                if (prev) {
                  skip(-(currentTime - prev.start));
                } else {
                  skip(-currentTime);
                }
              }}
            >
              <SkipBack className="h-3.5 w-3.5"/>
            </button>
            <button
              title="Next segment"
              className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              onClick={() => {
                const intervals = record?.tiers.concept?.intervals ?? [];
                const next = intervals
                  .filter(iv => iv.start > currentTime + 0.1)
                  .sort((a, b) => a.start - b.start)[0];
                if (next) {
                  skip(next.start - currentTime);
                }
              }}
            >
              <SkipForward className="h-3.5 w-3.5"/>
            </button>
            <div className="mx-2 h-5 w-px bg-slate-200"/>
            <button onClick={() => { const z = Math.max(10, zoom - 20); setZoom(z); wsSetZoom(z); }} title="Zoom out" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <ZoomOut className="h-3.5 w-3.5"/>
            </button>
            <div className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500">{zoom}px/s</div>
            <button onClick={() => { const z = Math.min(500, zoom + 20); setZoom(z); wsSetZoom(z); }} title="Zoom in" className="grid h-7 w-7 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800">
              <ZoomIn className="h-3.5 w-3.5"/>
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setSpectroOn(v => !v)}
              title="Toggle spectrogram"
              className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-semibold transition ${spectroOn ? 'bg-indigo-600 text-white' : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'}`}
            >
              <Activity className="h-3 w-3"/> Spectrogram
            </button>
          </div>
        </div>

        {/* Waveform container — WaveSurfer owns this div. The left padding on
            the inner wrapper matches the lane label gutter so waveform t=0
            lines up with segment t=0 in the STT/IPA/ORTH strips, without
            wrapping WaveSurfer's container in a flex row (which caused the
            container width to be unstable on first render and made the
            Timeline plugin flicker). */}
        <div className="relative px-5 pt-4 pb-2">
          <div className="relative" style={{ paddingLeft: LABEL_COL_PX }}>
            <div
              ref={containerRef}
              className="relative w-full overflow-hidden rounded-lg ring-1 ring-slate-100"
              style={{ minHeight: 110 }}
            />
            {spectroOn && (
              <canvas
                ref={spectroCanvasRef}
                className="pointer-events-none absolute inset-y-0 right-0 rounded-lg"
                style={{ left: LABEL_COL_PX, opacity: 0.6, mixBlendMode: 'multiply' }}
              />
            )}
          </div>
        </div>

        {/* Transcription lanes — STT / IPA / ORTH, toggled from the right drawer */}
        <TranscriptionLanes speaker={speaker} wsRef={wsRef} audioReady={audioReady} onSeek={seek}/>
      </section>

      {/* ======= CONCEPT HEADER ======= */}
      <section className="px-8 pt-6">
        <div className="mx-auto max-w-4xl">
          <div className="flex items-center gap-3">
            <button
              onClick={onPrev}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
            >
              <span>←</span>
              <span>Prev</span>
            </button>
            <div className="flex-1">
              <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Concept <span className="font-mono">#{concept.id}</span> <span>·</span> {concept.id} of {totalConcepts}
              </div>
              <div className="mt-0.5 flex items-center gap-3">
                <h1 className="text-[32px] font-semibold tracking-tight text-slate-900">{concept.name}</h1>
                <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-slate-700">
                  {speaker}
                </span>
                {annotated ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                    Annotated
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 ring-1 ring-rose-200">
                    Missing
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1 font-mono text-[11px] text-slate-400">
                <span className="text-[9px] uppercase tracking-wider text-slate-400">Source</span>
                <span className="text-slate-500">{speaker}.wav</span>
              </div>
            </div>
            <button
              onClick={onNext}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
            >
              <span>Next</span>
              <span>→</span>
            </button>
          </div>
        </div>
      </section>

      {/* ======= TRANSCRIPTION FIELDS ======= */}
      <section className="px-8 py-6">
        <div className="mx-auto max-w-4xl space-y-5">
          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">IPA Transcription</label>
            <input
              value={ipa}
              onChange={e => setIpa(e.target.value)}
              placeholder="Enter IPA…"
              dir="ltr"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-lg text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          <div>
            <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Orthographic (Kurdish)</label>
            <input
              value={ortho}
              onChange={e => setOrtho(e.target.value)}
              placeholder="Enter orthographic form…"
              dir="rtl"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-serif text-xl text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          {/* Timestamp editor for the current lexeme */}
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
                  onChange={e => setEditStart(e.target.value)}
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
                  onChange={e => setEditEnd(e.target.value)}
                  disabled={!conceptInterval}
                  className="w-28 rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1 font-mono text-xs text-slate-800 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
                />
              </div>
              <button
                data-testid="lexeme-timestamp-save"
                disabled={!conceptInterval || timestampSaving}
                onClick={async () => {
                  if (!conceptInterval) return;
                  const ns = parseFloat(editStart);
                  const ne = parseFloat(editEnd);
                  if (!Number.isFinite(ns) || !Number.isFinite(ne) || ne <= ns) {
                    setTimestampMessage({ kind: 'err', text: 'End must be greater than start.' });
                    return;
                  }
                  setTimestampSaving(true);
                  try {
                    const moved = moveIntervalAcrossTiers(speaker, conceptInterval.start, conceptInterval.end, ns, ne);
                    if (moved === 0) {
                      setTimestampMessage({ kind: 'err', text: 'No matching intervals found to retime.' });
                    } else {
                      await saveSpeaker(speaker);
                      setTimestampMessage({ kind: 'ok', text: `Retimed ${moved} tier${moved === 1 ? '' : 's'}.` });
                      addRegion(ns, ne);
                      seek(ns);
                    }
                  } catch (err) {
                    setTimestampMessage({ kind: 'err', text: err instanceof Error ? err.message : String(err) });
                  } finally {
                    setTimestampSaving(false);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5"/> Save timestamp
              </button>
              <button
                data-testid="lexeme-timestamp-reset"
                disabled={!conceptInterval}
                onClick={() => {
                  if (!conceptInterval) return;
                  setEditStart(conceptInterval.start.toFixed(3));
                  setEditEnd(conceptInterval.end.toFixed(3));
                  addRegion(conceptInterval.start, conceptInterval.end);
                  seek(conceptInterval.start);
                  setTimestampMessage(null);
                }}
                className="text-[11px] font-medium text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline disabled:opacity-50"
              >
                Reset
              </button>
              {timestampMessage && (
                <span data-testid="lexeme-timestamp-msg" className={`ml-auto text-[11px] ${timestampMessage.kind === 'ok' ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {timestampMessage.text}
                </span>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={() => {
                if (!selectedRegion) return;
                const interval = { start: selectedRegion.start, end: selectedRegion.end };
                setInterval(speaker, 'ipa', { ...interval, text: ipa });
                setInterval(speaker, 'ortho', { ...interval, text: ortho });
                setInterval(speaker, 'concept', { ...interval, text: concept.name });
                void saveSpeaker(speaker);
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700"
            >
              <Save className="h-4 w-4"/> Save Annotation
            </button>
            <button
              onClick={() => tagConcept('confirmed', concept.key)}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-semibold text-rose-600 transition hover:bg-rose-50"
            >
              <Check className="h-4 w-4"/> Mark Done
            </button>
            {onCaptureOffsetAnchor && (
              <div className="relative">
                <button
                  onClick={onCaptureOffsetAnchor}
                  data-testid="annotate-capture-anchor"
                  title="Anchor offset detection to this lexeme + the current playback time. Locks this lexeme against future global offset passes."
                  className="inline-flex items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2.5 text-sm font-semibold text-indigo-700 transition hover:bg-indigo-100"
                >
                  <Anchor className="h-4 w-4"/> Anchor offset here
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

      {/* ======= BOTTOM PLAYBACK BAR ======= */}
      <section className="sticky bottom-0 border-t border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-8 py-3">
          <button onClick={() => skip(-5)} title="-5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipBack className="h-4 w-4"/></button>
          <button onClick={() => skip(-1)} title="-1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronLeft className="h-4 w-4"/></button>
          <button
            onClick={handlePlayToggle}
            title={selectedRegion ? "Play selected region (Space)" : "Play (Space)"}
            data-testid="annotate-play"
            className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-white shadow-sm hover:bg-slate-700"
          >
            {isPlaying ? <Pause className="h-4 w-4"/> : <Play className="h-4 w-4 translate-x-[1px]"/>}
          </button>
          <button onClick={() => skip(1)} title="+1s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><ChevronRight className="h-4 w-4"/></button>
          <button onClick={() => skip(5)} title="+5s" className="grid h-8 w-8 place-items-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"><SkipForward className="h-4 w-4"/></button>

          <div className="ml-2 font-mono text-[11px] tabular-nums text-slate-500">
            {fmt(currentTime)} <span className="text-slate-300">/</span> {fmt(duration)}
          </div>

          <div className="ml-auto flex items-center gap-2">
            <select defaultValue="1" onChange={e => setRate(Number(e.target.value))} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 focus:border-indigo-300 focus:outline-none">
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
              title={canUndo ? `Undo ${nextUndoLabel} (⌘Z)` : 'Nothing to undo'}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Undo2 className="h-3 w-3"/> Undo
            </button>
            <button
              onClick={handleRedo}
              disabled={!canRedo}
              data-testid="annotate-redo"
              title={canRedo ? `Redo ${nextRedoLabel} (⇧⌘Z)` : 'Nothing to redo'}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Redo2 className="h-3 w-3"/> Redo
            </button>
            <button className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">
              <MessageSquare className="h-3 w-3"/> Chat
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
