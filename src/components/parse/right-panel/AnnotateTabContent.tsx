import { Activity, Anchor, Save } from 'lucide-react';

import type { RightPanelProps } from './types';
import { CollapsibleSection } from './CollapsibleSection';
import { TagsPanelSection } from './TagsPanelSection';
import { usePlaybackStore } from '../../../stores/playbackStore';
import { formatPlaybackTime } from '../../annotate/annotate-views/shared';

type AnnotateTabContentProps = Pick<
  RightPanelProps,
  | 'activeActionSpeaker'
  | 'offsetPhase'
  | 'onDetectOffset'
  | 'onOpenManualOffset'
  | 'onCaptureOffsetAnchor'
  | 'captureToast'
  | 'currentConceptId'
  | 'annotateSpeakerTools'
  | 'annotateAuxTools'
  | 'onSaveAnnotations'
>;

export function AnnotateTabContent({
  activeActionSpeaker,
  offsetPhase,
  onDetectOffset,
  onOpenManualOffset,
  onCaptureOffsetAnchor,
  captureToast,
  currentConceptId,
  annotateSpeakerTools,
  annotateAuxTools,
  onSaveAnnotations,
}: AnnotateTabContentProps) {
  const offsetButtonsDisabled = !activeActionSpeaker || offsetPhase === 'detecting' || offsetPhase === 'applying';
  const playheadSec = usePlaybackStore((s) => s.currentTime);

  return (
    <>
      <CollapsibleSection title="Timestamp tools" icon={<Anchor className="h-3 w-3" />}>
        <p className="mb-3 text-[10px] leading-snug text-slate-400">
          Shift every lexeme on this speaker by a constant offset. Lexemes you have manually retimed or anchored are protected and stay put.
        </p>

        {onCaptureOffsetAnchor && (
          <div className="mb-3">
            <div className="mb-1 px-1 text-[9px] font-semibold uppercase tracking-wider text-slate-400">Anchor</div>
            <div className="relative">
              <button
                onClick={onCaptureOffsetAnchor}
                data-testid="annotate-capture-anchor"
                title="Anchor offset detection to this lexeme + the current playback time. Locks this lexeme against future global offset passes."
                className="flex w-full items-center gap-2 rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-left text-[11px] font-semibold text-indigo-700 transition hover:bg-indigo-100"
              >
                <Anchor className="h-3 w-3" />
                <span className="flex-1">Anchor offset here</span>
                <span className="font-mono text-[10px] tabular-nums text-indigo-500">{formatPlaybackTime(playheadSec)}</span>
              </button>
              {captureToast && (
                <div
                  role="status"
                  data-testid="annotate-capture-toast"
                  className="absolute left-0 right-0 top-full mt-1 rounded-md border border-emerald-200 bg-white px-2 py-1 text-[10px] text-emerald-700 shadow-md"
                >
                  {captureToast}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mb-1 px-1 text-[9px] font-semibold uppercase tracking-wider text-slate-400">Detect</div>
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
      </CollapsibleSection>

      <TagsPanelSection conceptId={currentConceptId} speaker={activeActionSpeaker} />

      <CollapsibleSection title="Phonetic tools" icon={<Activity className="h-3 w-3" />}>
        <p className="mb-3 text-[10px] leading-snug text-slate-400">
          Tools operate on PARSE's virtual timeline — every action is scoped to the current audio segment.
        </p>

        {annotateSpeakerTools}
        {annotateAuxTools}
      </CollapsibleSection>

      <CollapsibleSection title="Annotation write" icon={<Save className="h-3 w-3" />} className="p-4">
        <button
          className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
          onClick={onSaveAnnotations}
        >
          <Save className="h-3 w-3" /> Save annotations
        </button>
      </CollapsibleSection>
    </>
  );
}
