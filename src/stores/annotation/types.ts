import type {
  AnnotationInterval,
  AnnotationRecord,
  ConfirmedAnchor,
  SttSegment,
} from "../../api/types";
import type { SpeakerHistory } from "../annotationStoreHistory";

export interface AnnotationStoreState {
  records: Record<string, AnnotationRecord>;
  dirty: Record<string, boolean>;
  loading: Record<string, boolean>;
  histories: Record<string, SpeakerHistory>;
}

export interface AnnotationStorePersistenceSlice {
  loadSpeaker: (speaker: string) => Promise<void>;
  saveSpeaker: (speaker: string) => Promise<void>;
}

export interface AnnotationStoreActionsSlice {
  setInterval: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  updateInterval: (speaker: string, tier: string, index: number, text: string) => void;
  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  removeInterval: (speaker: string, tier: string, index: number) => void;
  updateIntervalTimes: (
    speaker: string,
    tier: string,
    index: number,
    start: number,
    end: number,
  ) => void;
  mergeIntervals: (speaker: string, tier: string, index: number) => void;
  splitInterval: (speaker: string, tier: string, index: number, splitTime: number) => void;
  ensureSttTier: (speaker: string, segments: SttSegment[]) => void;
  ensureSttWordsTier: (speaker: string, segments: SttSegment[]) => void;
  setConfirmedAnchor: (
    speaker: string,
    conceptId: string,
    anchor: ConfirmedAnchor | null,
  ) => void;
  moveIntervalAcrossTiers: (
    speaker: string,
    oldStart: number,
    oldEnd: number,
    newStart: number,
    newEnd: number,
  ) => number;
  markLexemeManuallyAdjusted: (speaker: string, start: number, end: number) => number;
  undo: (speaker: string) => string | null;
  redo: (speaker: string) => string | null;
}

export type AnnotationStore = AnnotationStoreState
  & AnnotationStorePersistenceSlice
  & AnnotationStoreActionsSlice;

export type AnnotationStoreSet = (
  partial: Partial<AnnotationStore> | ((state: AnnotationStore) => Partial<AnnotationStore>),
) => void;

export type AnnotationStoreGet = () => AnnotationStore;

export type ScheduleAnnotationAutosave = (speaker: string) => void;
