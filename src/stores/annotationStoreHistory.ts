import type { AnnotationRecord } from "../api/types";
import { deepClone } from "./annotationStoreShared";

export interface HistoryEntry {
  snapshot: AnnotationRecord;
  label: string;
}

export interface SpeakerHistory {
  undo: HistoryEntry[];
  redo: HistoryEntry[];
}

export interface HistoryRestoreDelta {
  histories: Record<string, SpeakerHistory>;
  label: string;
  record: AnnotationRecord;
}

export const HISTORY_CAP = 50;

export function emptyHistory(): SpeakerHistory {
  return { undo: [], redo: [] };
}

export function pushHistoryDelta(
  histories: Record<string, SpeakerHistory>,
  speaker: string,
  pre: AnnotationRecord,
  label: string,
): Record<string, SpeakerHistory> {
  const prev = histories[speaker] ?? emptyHistory();
  const undo = [...prev.undo, { snapshot: deepClone(pre), label }];
  if (undo.length > HISTORY_CAP) undo.shift();
  return { ...histories, [speaker]: { undo, redo: [] } };
}

export function popUndoDelta(
  histories: Record<string, SpeakerHistory>,
  records: Record<string, AnnotationRecord>,
  speaker: string,
): HistoryRestoreDelta | null {
  const hist = histories[speaker];
  const current = records[speaker];
  if (!hist || hist.undo.length === 0 || !current) return null;

  const entry = hist.undo[hist.undo.length - 1];
  const nextUndo = hist.undo.slice(0, -1);
  const nextRedo = [...hist.redo, { snapshot: deepClone(current), label: entry.label }];

  return {
    label: entry.label,
    record: entry.snapshot,
    histories: {
      ...histories,
      [speaker]: { undo: nextUndo, redo: nextRedo },
    },
  };
}

export function popRedoDelta(
  histories: Record<string, SpeakerHistory>,
  records: Record<string, AnnotationRecord>,
  speaker: string,
): HistoryRestoreDelta | null {
  const hist = histories[speaker];
  const current = records[speaker];
  if (!hist || hist.redo.length === 0 || !current) return null;

  const entry = hist.redo[hist.redo.length - 1];
  const nextRedo = hist.redo.slice(0, -1);
  const nextUndo = [...hist.undo, { snapshot: deepClone(current), label: entry.label }];

  return {
    label: entry.label,
    record: entry.snapshot,
    histories: {
      ...histories,
      [speaker]: { undo: nextUndo, redo: nextRedo },
    },
  };
}
