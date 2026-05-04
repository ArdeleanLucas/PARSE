import { Activity, Anchor, AudioLines, Layers, Mic, Save, Scissors, SlidersHorizontal, Video } from 'lucide-react';

import type { RightPanelProps } from './types';
import { TagsPanelSection } from './TagsPanelSection';

type AnnotateTabContentProps = Pick<
  RightPanelProps,
  | 'activeActionSpeaker'
  | 'offsetPhase'
  | 'onDetectOffset'
  | 'onOpenManualOffset'
  | 'currentConceptId'
  | 'annotateSpeakerTools'
  | 'annotateAuxTools'
  | 'onSaveAnnotations'
>;

const phoneticToolCards = [
  { icon: AudioLines, label: 'Waveform view', hint: 'Segment-aware' },
  { icon: Video, label: 'Video clip', hint: 'Synced to timeline' },
  { icon: Scissors, label: 'Segment controls', hint: 'Split · Trim · Join' },
  { icon: SlidersHorizontal, label: 'Formant tracker', hint: 'Praat-compatible' },
  { icon: Mic, label: 'Re-record utterance', hint: 'Overlay on segment' },
] as const;

export function AnnotateTabContent({
  activeActionSpeaker,
  offsetPhase,
  onDetectOffset,
  onOpenManualOffset,
  currentConceptId,
  annotateSpeakerTools,
  annotateAuxTools,
  onSaveAnnotations,
}: AnnotateTabContentProps) {
  const offsetButtonsDisabled = !activeActionSpeaker || offsetPhase === 'detecting' || offsetPhase === 'applying';

  return (
    <>
      <div className="border-b border-slate-100 p-4">
        <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <Anchor className="h-3 w-3" /> Timestamp tools
        </h4>
        <p className="mb-3 text-[10px] leading-snug text-slate-400">
          Shift every lexeme on this speaker by a constant offset. Lexemes you have manually retimed or anchored are protected and stay put.
        </p>
        <div className="space-y-1.5">
          <button
            onClick={onDetectOffset}
            disabled={offsetButtonsDisabled}
            data-testid="drawer-detect-offset"
            className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Anchor className="h-3 w-3 text-slate-400" />
            {offsetPhase === 'detecting' ? 'Detecting offset…' : 'Detect Timestamp Offset'}
          </button>
          <button
            onClick={onOpenManualOffset}
            disabled={offsetButtonsDisabled}
            data-testid="drawer-detect-offset-manual"
            title="Skip auto-detect and anchor the offset from captured lexeme pairs directly."
            className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Anchor className="h-3 w-3 text-slate-400" />
            Detect offset (manual anchors)
          </button>
        </div>
      </div>

      <TagsPanelSection conceptId={currentConceptId} speaker={activeActionSpeaker} />

      <div className="border-b border-slate-100 p-4">
        <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <Activity className="h-3 w-3" /> Phonetic tools
        </h4>
        <p className="mb-3 text-[10px] leading-snug text-slate-400">
          Tools operate on PARSE's virtual timeline — every action is scoped to the current audio segment.
        </p>

        {annotateSpeakerTools}
        {annotateAuxTools}

        <button className="mb-1.5 flex w-full items-center gap-2 rounded-md bg-indigo-50 px-2.5 py-1.5 text-[11px] font-semibold text-indigo-800 ring-1 ring-indigo-200 hover:bg-indigo-100">
          <Layers className="h-3.5 w-3.5" />
          <span className="flex-1 text-left">Spectrogram workspace</span>
          <span className="rounded bg-white/70 px-1 font-mono text-[9px] text-indigo-600">ON</span>
        </button>

        <div className="space-y-1">
          {phoneticToolCards.map(({ icon: Icon, label, hint }) => (
            <button key={label} className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-slate-50">
              <Icon className="h-3.5 w-3.5 text-slate-400 group-hover:text-indigo-600" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[11px] font-medium text-slate-700">{label}</div>
                <div className="truncate text-[9px] text-slate-400">{hint}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="p-4">
        <button
          className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
          onClick={onSaveAnnotations}
        >
          <Save className="h-3 w-3" /> Save annotations
        </button>
      </div>
    </>
  );
}
