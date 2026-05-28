import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Pause,
  Play,
  Redo2,
  RotateCw,
  Save,
  Trash2,
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
import { rerunLexemeIpa, rerunLexemeOrtho, saveLexemeNote } from "../../../api/client";
import { LEXEME_RERUN_PAD_VALUES, type LexemeNoteEntry, type LexemeRerunPad, type LexemeRerunRequest } from "../../../api/types";
import { useEnrichmentStore } from "../../../stores/enrichmentStore";
import { parseRealizationKey } from "../../../lib/conceptGrouping";
import { LABEL_COL_PX, TranscriptionLanes } from "../TranscriptionLanes";
import { SpectrogramSettings } from "../SpectrogramSettings";

import { CreateLexemePanel } from "./CreateLexemePanel";
import { SpeakerHeader } from "./SpeakerHeader";
import { findAnnotationForConcept, formatPlaybackTime, formatPlayhead, formatSearchTime, pickOrthoIntervalForConcept } from "./shared";
import type { AnnotateViewProps } from "./types";

export { pickOrthoIntervalForConcept };

const SPEC_HEIGHT = 180;

type RerunField = "ipa" | "ortho";
type RerunDialogState = { field: RerunField; error: string | null } | null;

type LocalUndoEntry = { field: RerunField; value: string; orthoUserEdited?: boolean };

const DEFAULT_RERUN_PAD: LexemeRerunPad = 0.2;
const RERUN_PAD_OPTIONS: LexemeRerunPad[] = [...LEXEME_RERUN_PAD_VALUES];

function formatRerunPad(value: LexemeRerunPad): string {
  return value.toFixed(1);
}

function rerunRequestWithPad(request: LexemeRerunRequest, pad: LexemeRerunPad): LexemeRerunRequest {
  return { ...request, pad };
}

function truncatePreview(value: string): string {
  return value.length > 80 ? `${value.slice(0, 77)}…` : value;
}

export function extractRerunError(error: unknown): string {
  if (error instanceof Error) {
    if (/could not reach the parse api/i.test(error.message)) return "Network error. Try again.";
    if (error instanceof TypeError && /failed to fetch|networkerror/i.test(error.message)) return "Network error. Try again.";
    const match = error.message.match(/\{\s*"error"\s*:\s*"([^"]+)"\s*\}/);
    return match?.[1] ?? error.message;
  }
  return String(error || "Re-run failed.");
}

export const AnnotateView: React.FC<AnnotateViewProps> = ({
  concept,
  speaker,
  speakerConcepts,
  totalConcepts,
  onPrev,
  onNext,
  audioUrl,
  peaksUrl,
  surveyLabel,
  surveySourceItem,
  surveyChoices,
  resolvedSurveyId,
  availableSurveys,
  surveySettings,
  surveyColorCodingEnabled,
  activeSpeaker,
  conceptSurveyKey,
  selectedRealizationKey,
  onSurveyChoiceChange,
  onDeleteConcept,
}) => {
  const record = useAnnotationStore((s) => s.records[speaker] ?? null);
  const moveIntervalAcrossTiers = useAnnotationStore((s) => s.moveIntervalAcrossTiers);
  const saveLexemeAnnotation = useAnnotationStore((s) => s.saveLexemeAnnotation);
  const createConceptInterval = useAnnotationStore((s) => s.createConceptInterval);
  const saveSpeaker = useAnnotationStore((s) => s.saveSpeaker);
  const flushAutosave = useAnnotationStore((s) => s.flushAutosave);
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
    const local = localUndoRef.current.pop();
    if (local) {
      if (local.field === "ipa") {
        setIpa(local.value);
        setUndoToast("Undid IPA re-run");
      } else {
        setOrtho(local.value);
        setOrthoUserEdited(Boolean(local.orthoUserEdited));
        setUndoToast("Undid ORTH re-run");
      }
      return;
    }
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
  const enrichmentData = useEnrichmentStore((s) => s.data) as Record<string, unknown> | null;
  const saveEnrichments = useEnrichmentStore((s) => s.save);
  const isConfirmed = Boolean(record?.concept_tags?.[concept.key]?.includes("confirmed"));
  const confirmedAnchor = record?.confirmed_anchors?.[concept.key] ?? null;
  const focusedRealization = useMemo(
    () => parseRealizationKey(selectedRealizationKey ?? null),
    [selectedRealizationKey],
  );
  const focusedIntervalIndex = useMemo(() => {
    if (!focusedRealization) return undefined;
    if (focusedRealization.conceptId !== concept.key) return undefined;
    return focusedRealization.intervalIndex;
  }, [concept.key, focusedRealization]);
  const focusedLookupOptions = useMemo(
    () => ({ focusedIntervalIndex }),
    [focusedIntervalIndex],
  );
  const { conceptInterval, ipaInterval, orthoInterval, directOrthoInterval } = useMemo(
    () => findAnnotationForConcept(record, concept, focusedLookupOptions),
    [record, concept, focusedLookupOptions],
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
  const displayedOrthoText = directOrthoInterval ? directOrthoInterval.text : (orthoInterval?.text ?? "");
  const lexemeNotesBlock = useMemo(() => {
    const block = enrichmentData?.lexeme_notes;
    if (!block || typeof block !== "object") return undefined;
    const speakerBlock = (block as Record<string, unknown>)[speaker];
    if (!speakerBlock || typeof speakerBlock !== "object") return undefined;
    const entry = (speakerBlock as Record<string, unknown>)[concept.key];
    return (entry && typeof entry === "object" ? entry : undefined) as LexemeNoteEntry | undefined;
  }, [concept.key, enrichmentData, speaker]);
  const [ipa, setIpa] = useState(ipaInterval?.text ?? "");
  const [ortho, setOrtho] = useState(displayedOrthoText);
  const [orthoUserEdited, setOrthoUserEdited] = useState(false);
  const [editStart, setEditStart] = useState<string>(conceptInterval ? conceptInterval.start.toFixed(3) : "");
  const [editEnd, setEditEnd] = useState<string>(conceptInterval ? conceptInterval.end.toFixed(3) : "");
  const [timestampSaving, setTimestampSaving] = useState(false);
  const [timestampMessage, setTimestampMessage] = useState<{ kind: "ok"; text: string } | { kind: "err"; text: string } | null>(null);
  const [userNote, setUserNote] = useState(lexemeNotesBlock?.user_note ?? "");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [quickRetimeMenu, setQuickRetimeMenu] = useState<{ x: number; y: number; start: number; end: number } | null>(null);
  const [retimeAnotherMenu, setRetimeAnotherMenu] = useState<{ x: number; y: number; start: number; end: number } | null>(null);
  const [retimeAnotherQuery, setRetimeAnotherQuery] = useState("");
  const [retimeAnotherIndex, setRetimeAnotherIndex] = useState(0);
  const retimeAnotherDialogRef = useRef<HTMLDivElement | null>(null);
  const [createLexemeMenu, setCreateLexemeMenu] = useState<{ x: number; y: number; start: number; end: number } | null>(null);
  const [rerunDialog, setRerunDialog] = useState<RerunDialogState>(null);
  const [rerunBusy, setRerunBusy] = useState<RerunField | null>(null);
  const [rerunPad, setRerunPad] = useState<LexemeRerunPad>(DEFAULT_RERUN_PAD);
  const localUndoRef = useRef<LocalUndoEntry[]>([]);
  const rerunPrimaryRef = useRef<HTMLButtonElement | null>(null);
  const rerunCancelRef = useRef<HTMLButtonElement | null>(null);
  const rerunPadRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    setIpa(ipaInterval?.text ?? "");
    setOrtho(displayedOrthoText);
    setOrthoUserEdited(false);
    setEditStart(conceptInterval ? conceptInterval.start.toFixed(3) : "");
    setEditEnd(conceptInterval ? conceptInterval.end.toFixed(3) : "");
    setTimestampMessage(null);
    setNoteError(null);
    setSavingNote(false);
    setQuickRetimeMenu(null);
    setRetimeAnotherMenu(null);
    setRetimeAnotherQuery("");
    setRetimeAnotherIndex(0);
    setCreateLexemeMenu(null);
    setRerunDialog(null);
    setRerunBusy(null);
    setRerunPad(DEFAULT_RERUN_PAD);
    localUndoRef.current = [];
  }, [speaker, concept.key, conceptInterval, ipaInterval, displayedOrthoText]);

  useEffect(() => {
    setUserNote(lexemeNotesBlock?.user_note ?? "");
  }, [speaker, concept.key, lexemeNotesBlock?.user_note]);

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

  const handleCreateLexemeContextMenu = useCallback((selection: { start: number; end: number }, event: MouseEvent) => {
    event.preventDefault();
    setCreateLexemeMenu({ x: event.clientX, y: event.clientY, start: selection.start, end: selection.end });
  }, []);

  const {
    playPause,
    playRange,
    pause,
    seek,
    scrollToTimeAtFraction,
    skip,
    addRegion,
    clearQuickRetimeSelection,
    enableDragToCreate,
    disableDragToCreate,
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
  const saveOrthoText = directOrthoInterval ? ortho : (orthoUserEdited ? ortho : undefined);

  const pendingEdits = useMemo(() => {
    if (!conceptInterval) return false;
    const nextStart = parseFloat(editStart);
    const nextEnd = parseFloat(editEnd);
    const startChanged = Number.isFinite(nextStart) && Math.abs(nextStart - conceptInterval.start) > 1e-6;
    const endChanged = Number.isFinite(nextEnd) && Math.abs(nextEnd - conceptInterval.end) > 1e-6;
    const ipaChanged = ipa !== (ipaInterval?.text ?? "");
    return startChanged || endChanged || ipaChanged || orthoUserEdited;
  }, [conceptInterval, editEnd, editStart, ipa, ipaInterval, orthoUserEdited]);

  const handleMarkDone = useCallback(async () => {
    if (isConfirmed) return;
    let savedConceptInterval = conceptInterval;
    let savedIpaText = ipaInterval?.text ?? "";
    let savedOrthoText: string | undefined;
    let savedDirectOrthoText = directOrthoInterval?.text ?? undefined;

    if (conceptInterval && pendingEdits) {
      const parsedStart = parseFloat(editStart);
      const parsedEnd = parseFloat(editEnd);
      const nextStart = Number.isFinite(parsedStart) ? parsedStart : conceptInterval.start;
      const nextEnd = Number.isFinite(parsedEnd) ? parsedEnd : conceptInterval.end;
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
          orthoEdited: orthoUserEdited,
          conceptName: concept.name,
        });
        if (!result.ok) {
          setTimestampMessage({ kind: "err", text: result.error });
          return;
        }
        const saveResult = await saveSpeaker(speaker, record);
        if (saveResult?.record) {
          const reread = findAnnotationForConcept(saveResult.record, concept, focusedLookupOptions);
          savedConceptInterval = reread.conceptInterval ?? savedConceptInterval;
          savedIpaText = reread.ipaInterval?.text ?? savedIpaText;
          savedDirectOrthoText = reread.directOrthoInterval?.text ?? savedDirectOrthoText;
          savedOrthoText = reread.orthoInterval?.text ?? savedOrthoText;
        }
        if (savedConceptInterval) {
          storedIntervalRef.current = { start: savedConceptInterval.start, end: savedConceptInterval.end };
          setEditStart(savedConceptInterval.start.toFixed(3));
          setEditEnd(savedConceptInterval.end.toFixed(3));
          addRegion(savedConceptInterval.start, savedConceptInterval.end);
        }
        setTimestampMessage({ kind: "ok", text: `Saved (${result.moved} tier${result.moved === 1 ? "" : "s"} updated).` });
      } catch (err) {
        setTimestampMessage({ kind: "err", text: err instanceof Error ? err.message : String(err) });
        return;
      } finally {
        setTimestampSaving(false);
      }
    }

    setConceptTag(speaker, concept.key, "confirmed");
    if (savedConceptInterval) {
      setConfirmedAnchor(speaker, concept.key, {
        start: savedConceptInterval.start,
        end: savedConceptInterval.end,
        matched_text: savedDirectOrthoText || savedOrthoText || savedConceptInterval.text || savedIpaText || undefined,
        source: "user+confirmed_tag",
        confirmed_at: new Date().toISOString(),
      });
      setDoneToast("Marked done.");
    } else {
      setDoneToast("Marked done. Time anchor skipped: no boundary.");
    }
  }, [
    addRegion, concept, conceptInterval, directOrthoInterval, editEnd, editStart, focusedLookupOptions, ipa, ipaInterval,
    isConfirmed, orthoUserEdited, pendingEdits, record, saveLexemeAnnotation, saveOrthoText, saveSpeaker,
    setConceptTag, setConfirmedAnchor, speaker,
  ]);

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
        orthoEdited: orthoUserEdited,
        conceptName: concept.name,
      });
      if (!result.ok) {
        setTimestampMessage({ kind: "err", text: result.error });
        return;
      }
      const saveResult = await saveSpeaker(speaker, record);
      const savedConceptInterval = saveResult?.record ? findAnnotationForConcept(saveResult.record, concept, focusedLookupOptions).conceptInterval : null;
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
  }, [addRegion, clearQuickRetimeSelection, concept, conceptInterval, focusedLookupOptions, ipa, orthoUserEdited, quickRetimeMenu, record, saveLexemeAnnotation, saveOrthoText, saveSpeaker, seek, speaker]);

  const cancelQuickRetime = useCallback(() => {
    clearQuickRetimeSelection();
    setQuickRetimeMenu(null);
  }, [clearQuickRetimeSelection]);

  const cancelRetimeAnother = useCallback(() => {
    setRetimeAnotherMenu(null);
    setRetimeAnotherQuery("");
    setRetimeAnotherIndex(0);
  }, []);

  const openRetimeAnother = useCallback(() => {
    if (!quickRetimeMenu) return;
    setRetimeAnotherMenu(quickRetimeMenu);
    setRetimeAnotherQuery("");
    setRetimeAnotherIndex(0);
    setQuickRetimeMenu(null);
  }, [quickRetimeMenu]);

  const retimeAnotherChoices = useMemo(() => {
    const conceptsForSpeaker = speakerConcepts && speakerConcepts.length > 0 ? speakerConcepts : [concept];
    const query = retimeAnotherQuery.trim().toLowerCase();
    return conceptsForSpeaker
      .map((candidate) => {
        const lookup = findAnnotationForConcept(record, candidate);
        return {
          concept: candidate,
          currentInterval: lookup.conceptInterval,
          ipaInterval: lookup.ipaInterval,
          orthoInterval: lookup.directOrthoInterval,
        };
      })
      .filter(({ concept: candidate }) => {
        if (!query) return true;
        const names = [
          candidate.name,
          ...(candidate.mergedVariants ?? []).map((variant) => variant.conceptEn ?? ""),
          ...(candidate.variants ?? []).map((variant) => variant.conceptEn ?? ""),
        ];
        return names.some((name) => name.toLowerCase().includes(query));
      });
  }, [concept, record, retimeAnotherQuery, speakerConcepts]);

  useEffect(() => {
    if (retimeAnotherIndex < retimeAnotherChoices.length) return;
    setRetimeAnotherIndex(Math.max(0, retimeAnotherChoices.length - 1));
  }, [retimeAnotherChoices.length, retimeAnotherIndex]);

  useEffect(() => {
    if (!retimeAnotherMenu) return;
    const onMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && retimeAnotherDialogRef.current?.contains(target)) return;
      cancelRetimeAnother();
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [cancelRetimeAnother, retimeAnotherMenu]);

  const selectedRetimeAnotherChoice = retimeAnotherChoices[retimeAnotherIndex] ?? retimeAnotherChoices[0] ?? null;

  const retimeAnotherStatus = useCallback((targetConcept: typeof concept, currentInterval: typeof conceptInterval) => {
    if (!currentInterval) return "empty";
    const tags = record?.concept_tags?.[targetConcept.key] ?? [];
    if (tags.includes("problematic")) return "problematic";
    if (tags.includes("review-needed") || tags.includes("review")) return "review";
    return "annotated";
  }, [record?.concept_tags]);

  const retimeAnotherPillClasses = (status: string): string => {
    switch (status) {
      case "annotated":
        return "bg-emerald-50 text-emerald-700 ring-emerald-100";
      case "review":
        return "bg-amber-50 text-amber-700 ring-amber-100";
      case "problematic":
        return "bg-rose-50 text-rose-700 ring-rose-100";
      default:
        return "bg-slate-100 text-slate-500 ring-slate-200";
    }
  };

  const commitRetimeAnother = useCallback(async (choice = selectedRetimeAnotherChoice) => {
    if (!retimeAnotherMenu || !choice) return;
    try {
      if (choice.currentInterval) {
        const result = saveLexemeAnnotation({
          speaker,
          oldStart: choice.currentInterval.start,
          oldEnd: choice.currentInterval.end,
          newStart: retimeAnotherMenu.start,
          newEnd: retimeAnotherMenu.end,
          ipaText: choice.ipaInterval?.text ?? "",
          orthoText: choice.orthoInterval?.text ?? "",
          orthoEdited: false,
          conceptName: choice.concept.name,
        });
        if (!result.ok) {
          setTimestampMessage({ kind: "err", text: result.error });
          return;
        }
      } else {
        await createConceptInterval(speaker, choice.concept.key, retimeAnotherMenu.start, retimeAnotherMenu.end);
      }
      setTimestampMessage({ kind: "ok", text: choice.currentInterval ? `Updated ${choice.concept.name} timestamp` : `Created lexeme for ${choice.concept.name}` });
      clearQuickRetimeSelection();
      addRegion(retimeAnotherMenu.start, retimeAnotherMenu.end);
      seek(retimeAnotherMenu.start);
      cancelRetimeAnother();
    } catch (err) {
      setTimestampMessage({ kind: "err", text: err instanceof Error ? err.message : String(err || "Update failed.") });
    }
  }, [addRegion, cancelRetimeAnother, clearQuickRetimeSelection, createConceptInterval, retimeAnotherMenu, saveLexemeAnnotation, seek, selectedRetimeAnotherChoice, speaker]);

  const handleRetimeAnotherKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setRetimeAnotherIndex((value) => Math.min(retimeAnotherChoices.length - 1, value + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setRetimeAnotherIndex((value) => Math.max(0, value - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      void commitRetimeAnother();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelRetimeAnother();
    }
  }, [cancelRetimeAnother, commitRetimeAnother, retimeAnotherChoices.length]);

  const retimeAnotherDuration = retimeAnotherMenu ? Math.max(0, retimeAnotherMenu.end - retimeAnotherMenu.start) : 0;

  const commitCreateLexeme = useCallback(async () => {
    if (!createLexemeMenu) return;
    try {
      await createConceptInterval(speaker, concept.key, createLexemeMenu.start, createLexemeMenu.end);
      setCreateLexemeMenu(null);
    } catch (err) {
      setTimestampMessage({ kind: "err", text: err instanceof Error ? err.message : String(err || "Create lexeme failed.") });
    }
  }, [concept.key, createConceptInterval, createLexemeMenu, speaker]);

  const cancelCreateLexeme = useCallback(() => {
    setCreateLexemeMenu(null);
  }, []);

  const handleSaveNote = useCallback(async () => {
    setSavingNote(true);
    setNoteError(null);
    try {
      await saveLexemeNote({ speaker, concept_id: concept.key, user_note: userNote });
      await saveEnrichments({
        lexeme_notes: {
          [speaker]: {
            [concept.key]: {
              ...(lexemeNotesBlock ?? {}),
              user_note: userNote,
              updated_at: new Date().toISOString(),
            },
          },
        },
      });
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingNote(false);
    }
  }, [concept.key, lexemeNotesBlock, saveEnrichments, speaker, userNote]);

  useEffect(() => {
    if (!quickRetimeMenu && !createLexemeMenu && !retimeAnotherMenu) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (quickRetimeMenu) cancelQuickRetime();
      if (createLexemeMenu) cancelCreateLexeme();
      if (retimeAnotherMenu) cancelRetimeAnother();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [cancelCreateLexeme, cancelQuickRetime, cancelRetimeAnother, createLexemeMenu, quickRetimeMenu, retimeAnotherMenu]);

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

  const rerunRequest = useMemo(() => {
    if (!conceptInterval) return null;
    const parsedStart = parseFloat(editStart);
    const parsedEnd = parseFloat(editEnd);
    const start = Number.isFinite(parsedStart) ? parsedStart : conceptInterval.start;
    const end = Number.isFinite(parsedEnd) ? parsedEnd : conceptInterval.end;
    return { speaker, concept_key: concept.key, start, end };
  }, [concept.key, conceptInterval, editEnd, editStart, speaker]);

  const rerunIntervalLabel = rerunRequest
    ? `${rerunRequest.start.toFixed(3)} – ${rerunRequest.end.toFixed(3)} s · Δ ${(rerunRequest.end - rerunRequest.start).toFixed(3)}s · pad ${formatRerunPad(rerunPad)}s`
    : "No interval";

  const startRerun = useCallback((field: RerunField) => {
    if (!rerunRequest || rerunBusy) return;
    setRerunPad(DEFAULT_RERUN_PAD);
    setRerunDialog({ field, error: null });
  }, [rerunBusy, rerunRequest]);

  const confirmRerun = useCallback(async () => {
    if (!rerunDialog || !rerunRequest || !conceptInterval) return;
    const dialogField = rerunDialog.field;
    setRerunBusy(dialogField);
    setRerunDialog((current) => current ? { ...current, error: null } : current);

    const apiRequest = rerunRequestWithPad(rerunRequest, rerunPad);
    let apiResultText: string;
    try {
      if (dialogField === "ipa") {
        const result = await rerunLexemeIpa(apiRequest);
        apiResultText = result.ipa;
      } else {
        const result = await rerunLexemeOrtho(apiRequest);
        apiResultText = result.ortho;
      }
    } catch (error) {
      const message = extractRerunError(error);
      setRerunDialog((current) => current ? { ...current, error: message } : current);
      setRerunBusy(null);
      return;
    }

    const saveResult = saveLexemeAnnotation({
      speaker,
      oldStart: conceptInterval.start,
      oldEnd: conceptInterval.end,
      newStart: rerunRequest.start,
      newEnd: rerunRequest.end,
      ipaText: dialogField === "ipa" ? apiResultText : ipa,
      orthoText: dialogField === "ortho" ? apiResultText : saveOrthoText,
      orthoEdited: dialogField === "ortho" ? true : orthoUserEdited,
      conceptName: concept.name,
    });
    if (!saveResult.ok) {
      setRerunDialog((current) => current ? { ...current, error: saveResult.error } : current);
      setRerunBusy(null);
      return;
    }

    if (dialogField === "ipa") {
      localUndoRef.current.push({ field: "ipa", value: ipa });
      setIpa(apiResultText);
    } else {
      localUndoRef.current.push({ field: "ortho", value: ortho, orthoUserEdited });
      setOrtho(apiResultText);
      setOrthoUserEdited(true);
    }

    try {
      await saveSpeaker(speaker, record);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setTimestampMessage({ kind: "err", text: message });
      setRerunDialog(null);
      setRerunBusy(null);
      setRerunPad(DEFAULT_RERUN_PAD);
      return;
    }

    setUndoToast(dialogField === "ipa"
      ? `Re-ran IPA — saved "${truncatePreview(apiResultText)}"`
      : `Re-ran ORTH — saved "${truncatePreview(apiResultText)}"`);
    setRerunDialog(null);
    setRerunBusy(null);
    setRerunPad(DEFAULT_RERUN_PAD);
  }, [concept.name, conceptInterval, ipa, ortho, orthoUserEdited, record, rerunDialog, rerunPad, rerunRequest, saveLexemeAnnotation, saveOrthoText, saveSpeaker, speaker]);

  const closeRerunDialog = useCallback(() => {
    if (rerunBusy) return;
    setRerunDialog(null);
    setRerunPad(DEFAULT_RERUN_PAD);
  }, [rerunBusy]);

  useEffect(() => {
    if (!rerunDialog) return;
    const previousActive = document.activeElement as HTMLElement | null;
    const focusId = window.setTimeout(() => rerunPrimaryRef.current?.focus(), 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRerunDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const first = rerunPadRefs.current[0] ?? rerunCancelRef.current;
      const last = rerunPrimaryRef.current;
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusId);
      window.removeEventListener("keydown", onKeyDown);
      previousActive?.focus?.();
    };
  }, [closeRerunDialog, rerunDialog]);

  const rerunButtonClass = "inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-indigo-700 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50";

  const renderRerunButton = (field: RerunField) => {
    const busy = rerunBusy === field;
    return (
      <button
        type="button"
        data-testid={field === "ipa" ? "run-ipa-button" : "run-orth-button"}
        disabled={!conceptInterval || Boolean(rerunBusy)}
        onClick={() => startRerun(field)}
        className={rerunButtonClass}
      >
        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCw className="h-3 w-3" />}
        {busy ? "Running…" : field === "ipa" ? "Run IPA" : "Run ORTH"}
      </button>
    );
  };

  const handleRerunPadKeyDown = useCallback((value: LexemeRerunPad, event: React.KeyboardEvent<HTMLButtonElement>) => {
    const index = RERUN_PAD_OPTIONS.indexOf(value);
    const direction = event.key === "ArrowRight" || event.key === "ArrowDown"
      ? 1
      : event.key === "ArrowLeft" || event.key === "ArrowUp"
        ? -1
        : 0;
    if (!direction || index < 0) return;
    event.preventDefault();
    const nextIndex = (index + direction + RERUN_PAD_OPTIONS.length) % RERUN_PAD_OPTIONS.length;
    setRerunPad(RERUN_PAD_OPTIONS[nextIndex]);
    window.setTimeout(() => rerunPadRefs.current[nextIndex]?.focus(), 0);
  }, []);

  const rerunDialogValue = rerunDialog?.field === "ipa" ? ipa : ortho;
  const rerunDialogTitle = rerunDialog?.field === "ipa" ? "Overwrite IPA transcription?" : "Overwrite orthographic form?";
  const rerunDialogPrimary = rerunDialog?.field === "ipa" ? "Run IPA & overwrite" : "Run ORTH & overwrite";

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
            {createLexemeMenu && (
              <div
                role="menu"
                aria-label="Waveform create lexeme menu"
                className="fixed z-50 min-w-52 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
                style={{ left: createLexemeMenu.x, top: createLexemeMenu.y }}
                onContextMenu={(event) => event.preventDefault()}
              >
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full px-3 py-2 text-left text-slate-700 hover:bg-slate-50"
                  onClick={() => void commitCreateLexeme()}
                >
                  Create lexeme for {concept.name}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full border-t border-slate-100 px-3 py-2 text-left text-slate-600 hover:bg-slate-50"
                  onClick={cancelCreateLexeme}
                >
                  Cancel selection
                </button>
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
                  className="block w-full border-y border-slate-100 px-3 py-2 text-left text-slate-700 hover:bg-slate-50"
                  onClick={openRetimeAnother}
                >
                  Update another timestamp…
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="block w-full px-3 py-2 text-left text-slate-600 hover:bg-slate-50"
                  onClick={cancelQuickRetime}
                >
                  Cancel selection
                </button>
              </div>
            )}
            {retimeAnotherMenu && (
              <div
                ref={retimeAnotherDialogRef}
                role="dialog"
                aria-label="Move highlighted region to another concept"
                className="fixed z-50 w-[420px] overflow-hidden rounded-xl border border-slate-200 bg-white text-sm shadow-xl"
                style={{ left: retimeAnotherMenu.x, top: retimeAnotherMenu.y }}
                onContextMenu={(event) => event.preventDefault()}
                onKeyDown={handleRetimeAnotherKeyDown}
              >
                <div className="border-b border-slate-100 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-sm font-semibold text-slate-900">Move highlighted region to another concept</h2>
                      <p className="mt-1 text-xs text-slate-500">
                        New timestamp: {formatSearchTime(retimeAnotherMenu.start)} – {formatSearchTime(retimeAnotherMenu.end)} ({retimeAnotherDuration.toFixed(3)}s)
                      </p>
                    </div>
                    <button
                      type="button"
                      aria-label="Close concept picker"
                      className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      onClick={cancelRetimeAnother}
                    >
                      ×
                    </button>
                  </div>
                  <input
                    autoFocus
                    value={retimeAnotherQuery}
                    onChange={(event) => {
                      setRetimeAnotherQuery(event.target.value);
                      setRetimeAnotherIndex(0);
                    }}
                    placeholder="Search concepts on this speaker…"
                    className="mt-3 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
                  />
                </div>
                <div role="listbox" aria-label="Concepts on this speaker" className="max-h-72 overflow-y-auto py-1">
                  {retimeAnotherChoices.length === 0 ? (
                    <div className="px-4 py-5 text-center text-sm text-slate-500">No concepts match this search.</div>
                  ) : retimeAnotherChoices.map((choice, index) => {
                    const status = retimeAnotherStatus(choice.concept, choice.currentInterval);
                    const selected = index === retimeAnotherIndex;
                    return (
                      <button
                        key={choice.concept.key}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        className={`block w-full px-4 py-2.5 text-left transition ${selected ? "bg-indigo-50" : "hover:bg-slate-50"}`}
                        onClick={() => setRetimeAnotherIndex(index)}
                        onDoubleClick={() => void commitRetimeAnother(choice)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate font-medium text-slate-900">{choice.concept.name}</div>
                            {choice.currentInterval ? (
                              <div className="mt-0.5 text-xs text-slate-500">
                                current: {formatSearchTime(choice.currentInterval.start)} – {formatSearchTime(choice.currentInterval.end)}
                                <span className="text-indigo-400"> → {formatSearchTime(retimeAnotherMenu.start)} – {formatSearchTime(retimeAnotherMenu.end)}</span>
                              </div>
                            ) : (
                              <div className="mt-0.5 text-xs italic text-slate-400">no current timestamp</div>
                            )}
                          </div>
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${retimeAnotherPillClasses(status)}`}>
                            {status}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
                  <div className="text-[11px] text-slate-400">↑/↓ select · Enter update · Esc close</div>
                  <div className="flex items-center gap-2">
                    <button type="button" className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100" onClick={cancelRetimeAnother}>
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={!selectedRetimeAnotherChoice}
                      className={`rounded-lg px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300 ${selectedRetimeAnotherChoice?.currentInterval ? "bg-indigo-600 hover:bg-indigo-700" : "bg-emerald-600 hover:bg-emerald-700"}`}
                      onClick={() => void commitRetimeAnother()}
                    >
                      {selectedRetimeAnotherChoice?.currentInterval
                        ? `Update ${selectedRetimeAnotherChoice.concept.name}`
                        : selectedRetimeAnotherChoice
                          ? `Create lexeme for ${selectedRetimeAnotherChoice.concept.name}`
                          : "Update concept"}
                    </button>
                  </div>
                </div>
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
        surveyLabel={surveyLabel}
        surveySourceItem={surveySourceItem}
        surveyChoices={surveyChoices}
        resolvedSurveyId={resolvedSurveyId}
        availableSurveys={availableSurveys}
        surveySettings={surveySettings}
        surveyColorCodingEnabled={surveyColorCodingEnabled}
        activeSpeaker={activeSpeaker}
        conceptSurveyKey={conceptSurveyKey}
        onSurveyChoiceChange={onSurveyChoiceChange}
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
            <div className="flex items-center justify-between gap-3">
              <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">IPA Transcription</label>
              {renderRerunButton("ipa")}
            </div>
            <input
              value={ipa}
              onChange={(e) => setIpa(e.target.value)}
              placeholder="Enter IPA…"
              dir="ltr"
              className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-mono text-lg text-slate-900 placeholder:text-slate-300 focus:border-indigo-300 focus:outline-none focus:ring-4 focus:ring-indigo-50"
            />
          </div>

          <div>
            <div className="flex items-center justify-between gap-3">
              <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Orthographic</label>
              {renderRerunButton("ortho")}
            </div>
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

          {conceptInterval ? (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
              <div className="mb-2 flex items-center justify-between">
                <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Lexeme timestamp (seconds)</label>
                <span className="font-mono text-[10px] text-slate-400">{fmt(conceptInterval.start)}–{fmt(conceptInterval.end)}</span>
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
                    className="w-28 rounded-md border border-slate-200 bg-slate-50/70 px-2 py-1 font-mono text-xs text-slate-800 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:opacity-50"
                  />
                </div>
                <button
                  type="button"
                  data-testid="confirm-time"
                  aria-pressed={Boolean(confirmedAnchor)}
                  title="Confirms the lexeme boundaries without requiring transcription. Used by cross-speaker anchor discovery in lexeme_search Signal B, audio re-STT priors, forced-alignment training data, and future audio-similarity discovery."
                  disabled={timestampSaving}
                  onClick={async () => {
                    const nextStart = parseFloat(editStart);
                    const nextEnd = parseFloat(editEnd);
                    const start = Number.isFinite(nextStart) ? nextStart : conceptInterval.start;
                    const end = Number.isFinite(nextEnd) ? nextEnd : conceptInterval.end;
                    const startChanged = Math.abs(start - conceptInterval.start) > 1e-6;
                    const endChanged = Math.abs(end - conceptInterval.end) > 1e-6;
                    if (confirmedAnchor && !startChanged && !endChanged) {
                      setConfirmedAnchor(speaker, concept.key, null);
                      flushAutosave(speaker);
                      setTimestampMessage({ kind: "ok", text: "Boundary confirmation cleared." });
                      return;
                    }
                    if (startChanged || endChanged) {
                      setTimestampSaving(true);
                      try {
                        const result = saveLexemeAnnotation({
                          speaker,
                          oldStart: conceptInterval.start,
                          oldEnd: conceptInterval.end,
                          newStart: start,
                          newEnd: end,
                          ipaText: ipa,
                          orthoText: saveOrthoText,
                          orthoEdited: orthoUserEdited,
                          conceptName: concept.name,
                        });
                        if (!result.ok) {
                          setTimestampMessage({ kind: "err", text: result.error });
                          return;
                        }
                      } finally {
                        setTimestampSaving(false);
                      }
                    }
                    setConfirmedAnchor(speaker, concept.key, {
                      start,
                      end,
                      source: "user+boundary_only",
                      confirmed_at: new Date().toISOString(),
                    });
                    const saveResult = await saveSpeaker(speaker, record);
                    const saved = saveResult?.record ? findAnnotationForConcept(saveResult.record, concept, focusedLookupOptions).conceptInterval : null;
                    if (saved) {
                      storedIntervalRef.current = { start: saved.start, end: saved.end };
                      setEditStart(saved.start.toFixed(3));
                      setEditEnd(saved.end.toFixed(3));
                      addRegion(saved.start, saved.end);
                    }
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
          ) : (
            <CreateLexemePanel
              speaker={speaker}
              conceptKey={concept.key}
              enableDragToCreate={enableDragToCreate}
              disableDragToCreate={disableDragToCreate}
              onContextMenu={handleCreateLexemeContextMenu}
            />
          )}

          <div className="flex items-center gap-3 pt-2">
            {conceptInterval && (
              <button
                data-testid="save-lexeme-annotation"
                disabled={timestampSaving}
                onClick={async () => {
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
                      orthoEdited: orthoUserEdited,
                      conceptName: concept.name,
                    });
                    if (!result.ok) {
                      setTimestampMessage({ kind: "err", text: result.error });
                    } else {
                      const saveResult = await saveSpeaker(speaker, record);
                      const savedConceptInterval = saveResult?.record ? findAnnotationForConcept(saveResult.record, concept, focusedLookupOptions).conceptInterval : null;
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
            )}
            <button
              type="button"
              data-testid="annotate-delete-concept"
              onClick={onDeleteConcept}
              className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-semibold text-rose-700 shadow-sm transition hover:bg-rose-50 hover:text-rose-800"
            >
              <Trash2 className="h-4 w-4" /> Delete concept
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
      {rerunDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeRerunDialog();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="rerun-confirm-title"
            data-testid="rerun-confirm-modal"
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <h2 id="rerun-confirm-title" className="text-base font-semibold text-slate-900">{rerunDialogTitle}</h2>
            <p className="mt-2 text-sm text-slate-600">
              This will replace the current value. This action can be undone with ⌘Z.
            </p>
            <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600">
              {rerunIntervalLabel}
            </div>
            <div className="mt-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">Audio context pad</div>
              <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Audio context pad">
                {RERUN_PAD_OPTIONS.map((value, index) => {
                  const selected = rerunPad === value;
                  const label = value === DEFAULT_RERUN_PAD ? `${formatRerunPad(value)} s · default` : `${formatRerunPad(value)} s`;
                  return (
                    <button
                      key={value}
                      type="button"
                      ref={(node) => { rerunPadRefs.current[index] = node; }}
                      data-testid={`rerun-pad-${formatRerunPad(value)}`}
                      aria-pressed={selected}
                      disabled={Boolean(rerunBusy)}
                      onClick={() => setRerunPad(value)}
                      onKeyDown={(event) => handleRerunPadKeyDown(value, event)}
                      className={
                        "rounded-full border px-3 py-1 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 " +
                        (selected
                          ? "border-indigo-600 bg-indigo-600 text-white shadow-sm"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50")
                      }
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="mt-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">Current value</div>
              <div
                dir={rerunDialog.field === "ortho" ? "rtl" : "ltr"}
                className={`mt-1 min-h-10 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 ${rerunDialog.field === "ortho" ? "font-serif" : "font-mono"}`}
              >
                {truncatePreview(rerunDialogValue) || "Empty"}
              </div>
            </div>
            {rerunDialog.error ? (
              <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {rerunDialog.error}
              </div>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                ref={rerunCancelRef}
                data-testid="rerun-confirm-cancel"
                disabled={Boolean(rerunBusy)}
                onClick={closeRerunDialog}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                ref={rerunPrimaryRef}
                data-testid="rerun-confirm-primary"
                disabled={Boolean(rerunBusy)}
                onClick={() => void confirmRerun()}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {rerunBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
                {rerunDialogPrimary}
              </button>
            </div>
          </div>
        </div>
      )}
      {settingsAnchor && (
        <SpectrogramSettings
          anchor={settingsAnchor}
          onClose={() => setSettingsAnchor(null)}
        />
      )}
    </main>
  );
};
