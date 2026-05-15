import type { ReactNode } from 'react';
import type { ConceptSurveyLinksByConcept, SpeakerConceptSurveyLinks, SurveyOverlapPatch, SpeakerSurveyChoices, SurveySettingsMap } from '../../../api/types';
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
  onSelectAllSpeakers: () => void;
  onClearSpeakers: () => void;
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
  onCaptureOffsetAnchor?: () => void;
  captureToast?: string | null;
  currentConceptId: string;
  annotateSpeakerTools?: ReactNode;
  annotateAuxTools?: ReactNode;
  onSaveAnnotations: () => void;
  activeConcept?: Concept | null;
  workspaceConcepts?: Concept[];
  conceptSurveyLinks?: ConceptSurveyLinksByConcept;
  speakerConceptSurveyLinks?: SpeakerConceptSurveyLinks;
  surveyColorCodingEnabled: boolean;
  surveySettings: SurveySettingsMap;
  speakerSurveyChoices: SpeakerSurveyChoices;
  onSurveyOverlapUpdate: (patch: SurveyOverlapPatch) => void;
  onSurveyChoiceChange?: (speaker: string, conceptKey: string, surveyId: string) => void;
  onPromoteSurveyPrimary?: (conceptId: string, surveyId: string, sourceItem: string) => void | Promise<void>;
  onRelinkApplied?: () => void | Promise<void>;
}

export interface SpeakersSectionProps {
  currentMode: AppMode;
  selectedSpeakers: string[];
  speakers: string[];
  speakerPicker: string | null;
  onSpeakerSelect: (speaker: string) => void;
  onAddSpeaker: () => void;
  onToggleSpeaker: (speaker: string) => void;
  onSelectAllSpeakers: () => void;
  onClearSpeakers: () => void;
}
