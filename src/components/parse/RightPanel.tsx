import { PanelRightClose } from 'lucide-react';

import { AnnotateTabContent, collapsedPanelIcons, CompareTabContent, SpeakersSection } from './right-panel';
import type { RightPanelProps } from './right-panel';

export type { RightPanelProps } from './right-panel';

export function RightPanel(props: RightPanelProps) {
  const { panelOpen, onTogglePanel, currentMode } = props;

  return (
    <aside
      className={`relative shrink-0 border-l border-slate-200/80 bg-white transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${panelOpen ? 'w-[250px]' : 'w-[52px]'}`}
      data-testid="right-panel"
    >
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/90 px-3 py-2.5 backdrop-blur">
        <span className={`text-[10px] font-semibold uppercase tracking-wider text-slate-500 transition-opacity duration-300 ${panelOpen ? 'opacity-100' : 'opacity-0'}`}>
          Controls
        </span>
        <button
          onClick={onTogglePanel}
          title={panelOpen ? 'Collapse' : 'Expand'}
          className="grid h-7 w-7 place-items-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
        >
          <PanelRightClose className={`h-3.5 w-3.5 transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${panelOpen ? '' : 'rotate-180'}`} />
        </button>
      </div>

      <div className={`absolute inset-x-0 top-[46px] flex flex-col items-center gap-1 py-3 transition-opacity duration-300 ${panelOpen ? 'pointer-events-none opacity-0' : 'opacity-100 delay-200'}`}>
        {collapsedPanelIcons.map(({ icon: Icon, label }) => (
          <button
            key={label}
            title={label}
            onClick={onTogglePanel}
            className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-indigo-50 hover:text-indigo-600"
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}
      </div>

      <div
        className={`h-[calc(100%-46px)] overflow-y-auto overflow-x-hidden transition-opacity duration-300 ${panelOpen ? 'opacity-100 delay-200' : 'pointer-events-none opacity-0'}`}
        style={{ width: 250 }}
      >
        <SpeakersSection
          currentMode={props.currentMode}
          selectedSpeakers={props.selectedSpeakers}
          speakers={props.speakers}
          speakerPicker={props.speakerPicker}
          onSpeakerSelect={props.onSpeakerSelect}
          onAddSpeaker={props.onAddSpeaker}
          onToggleSpeaker={props.onToggleSpeaker}
        />

        {currentMode === 'compare' ? (
          <CompareTabContent
            selectedSpeakers={props.selectedSpeakers}
            conceptCount={props.conceptCount}
            speakers={props.speakers}
            computeMode={props.computeMode}
            onComputeModeChange={props.onComputeModeChange}
            onComputeRun={props.onComputeRun}
            crossSpeakerJobStatus={props.crossSpeakerJobStatus}
            computeJobStatus={props.computeJobStatus}
            computeJobProgress={props.computeJobProgress}
            computeJobEtaMs={props.computeJobEtaMs}
            computeJobError={props.computeJobError}
            clefConfigured={props.clefConfigured}
            onOpenSourcesReport={props.onOpenSourcesReport}
            onOpenClefConfig={props.onOpenClefConfig}
            onRefreshEnrichments={props.onRefreshEnrichments}
            onOpenLoadDecisions={props.onOpenLoadDecisions}
            onSaveDecisions={props.onSaveDecisions}
            onExportLingPy={props.onExportLingPy}
            exporting={props.exporting}
            onOpenCommentsImport={props.onOpenCommentsImport}
          />
        ) : (
          <AnnotateTabContent
            activeActionSpeaker={props.activeActionSpeaker}
            offsetPhase={props.offsetPhase}
            onDetectOffset={props.onDetectOffset}
            onOpenManualOffset={props.onOpenManualOffset}
            currentConceptId={props.currentConceptId}
            annotateSpeakerTools={props.annotateSpeakerTools}
            annotateAuxTools={props.annotateAuxTools}
            onSaveAnnotations={props.onSaveAnnotations}
          />
        )}
      </div>
    </aside>
  );
}
