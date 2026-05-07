import type { ReactNode } from 'react';
import type { SurveyOverlapPatch, SpeakerSurveyChoices, SurveySettingsMap } from '../../../api/types';
import type { Concept } from '../../../lib/speakerForm';
import type { CompareComputeJobStatus, CompareComputeMode, OffsetPhase } from '../compareComputeContract';

export type AppMode = 'annotate' | 'compare' | 'tags';

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
  onOpenLoadDecisions: () => void;
  onSaveDecisions: () => void;
  onExportLingPy: () => void;
  exporting: boolean;
  onOpenCommentsImport: () => void;
  activeActionSpeaker: string | null;
  offsetPhase: OffsetPhase;
  onDetectOffset: () => void;
  onOpenManualOffset: () => void;
  currentConceptId: string;
  annotateSpeakerTools?: ReactNode;
  annotateAuxTools?: ReactNode;
  onSaveAnnotations: () => void;
  activeConcept?: Concept | null;
  surveyColorCodingEnabled: boolean;
  surveySettings: SurveySettingsMap;
  speakerSurveyChoices: SpeakerSurveyChoices;
  onSurveyOverlapUpdate: (patch: SurveyOverlapPatch) => void;
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
