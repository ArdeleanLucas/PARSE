import type { ReactNode } from 'react';
import type { CompareComputeJobStatus, CompareComputeMode, OffsetPhase } from '../compareComputeContract';

export type AppMode = 'annotate' | 'compare' | 'tags';

export type CompareTagFilter = 'all' | 'untagged' | 'review' | 'confirmed' | 'problematic' | string;

export interface RightPanelProps {
  panelOpen: boolean;
  onTogglePanel: () => void;
  currentMode: AppMode;
  selectedSpeakers: string[];
  speakers: string[];
  conceptCount: number;
  speakerPicker: string | null;
  onSpeakerSelect: (speaker: string) => void;
  onAddSpeaker: () => void;
  onToggleSpeaker: (speaker: string) => void;
  computeMode: CompareComputeMode;
  onComputeModeChange: (mode: CompareComputeMode) => void;
  onComputeRun: () => void;
  crossSpeakerJobStatus: CompareComputeJobStatus;
  computeJobStatus: CompareComputeJobStatus;
  computeJobProgress: number;
  computeJobEtaMs: number | null;
  computeJobError: string | null;
  clefConfigured: boolean | null;
  onOpenSourcesReport: () => void;
  onOpenClefConfig: () => void;
  onRefreshEnrichments: () => void;
  tagFilter: CompareTagFilter;
  onTagFilterChange: (filter: CompareTagFilter) => void;
  onOpenLoadDecisions: () => void;
  onSaveDecisions: () => void;
  onExportLingPy: () => void;
  exporting: boolean;
  onOpenCommentsImport: () => void;
  activeActionSpeaker: string | null;
  offsetPhase: OffsetPhase;
  onDetectOffset: () => void;
  onOpenManualOffset: () => void;
  annotateSpeakerTools?: ReactNode;
  annotateAuxTools?: ReactNode;
  onSaveAnnotations: () => void;
}

export interface SpeakersSectionProps {
  currentMode: AppMode;
  selectedSpeakers: string[];
  speakers: string[];
  speakerPicker: string | null;
  onSpeakerSelect: (speaker: string) => void;
  onAddSpeaker: () => void;
  onToggleSpeaker: (speaker: string) => void;
}
