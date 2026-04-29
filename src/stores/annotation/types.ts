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

export interface SaveSpeakerResult {
  record: AnnotationRecord;
  changedTiers: string[];
}

export interface AnnotationStorePersistenceSlice {
  loadSpeaker: (speaker: string) => Promise<void>;
  saveSpeaker: (speaker: string, baseline?: AnnotationRecord | null) => Promise<SaveSpeakerResult>;
}

export interface SaveLexemeAnnotationPayload {
  speaker: string;
  oldStart: number;
  oldEnd: number;
  newStart: number;
  newEnd: number;
  ipaText: string;
  orthoText: string;
  conceptName: string;
}

export type SaveLexemeAnnotationResult =
  | { ok: true; moved: number }
  | { ok: false; error: string };

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
    tierScope?: readonly string[],
  ) => number;
  saveLexemeAnnotation: (payload: SaveLexemeAnnotationPayload) => SaveLexemeAnnotationResult;
  markLexemeManuallyAdjusted: (speaker: string, start: number, end: number) => number;
  applyConceptScopedRefresh: (speaker: string, targets: readonly unknown[]) => number;
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
