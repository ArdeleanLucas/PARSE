import type { AnnotationInterval, AnnotationRecord } from "../../../api/types";

export interface Concept {
  id: number | string;
  key: string;
  name: string;
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

export interface AnnotationPanelProps {
  onAnnotationSaved?: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  onSeek?: (timeSec: number) => void;
}

export interface LexemeSearchPanelProps {
  onSeek?: (timeSec: number) => void;
}

export interface AnnotationLookup {
  conceptInterval: AnnotationInterval | null;
  ipaInterval: AnnotationInterval | null;
  orthoInterval: AnnotationInterval | null;
}

export interface SegmentSelection {
  speaker: string;
  tier: string;
  index: number;
}

export interface SegmentEditorProps {
  speaker: string | null;
  currentTime: number;
  selected: SegmentSelection | null;
  record: AnnotationRecord | null;
  onUpdateText: (speaker: string, tier: string, index: number, text: string) => void;
  onUpdateTimes: (speaker: string, tier: string, index: number, start: number, end: number) => void;
  onMerge: (speaker: string, tier: string, index: number) => void;
  onSplit: (speaker: string, tier: string, index: number, splitTime: number) => void;
  onDelete: (tier: string, index: number) => void;
  onClearSelection: () => void;
}

export const PANEL_TABS = ["annotation", "transcript", "suggestions", "chat"] as const;
export type AnnotatePanelTab = (typeof PANEL_TABS)[number];

export const RATE_OPTIONS = [
  { value: "0.5", label: "0.5x" },
  { value: "0.75", label: "0.75x" },
  { value: "1", label: "1.0x" },
  { value: "1.25", label: "1.25x" },
] as const;
