import { AlertCircle, Anchor, CheckCircle2, Loader2, Plus, X } from 'lucide-react';
import type { OffsetDetectResult } from '../../../api/client';
import { Modal } from '../../shared/Modal';
import { formatPlaybackTime, type ManualAnchor, type ManualConsensus, type OffsetState } from '../../../hooks/useOffsetState';

interface OffsetAdjustmentModalProps {
  open: boolean;
  offsetState: OffsetState;
  manualAnchors: ManualAnchor[];
  manualConsensus: ManualConsensus | null;
  manualBusy: boolean;
  protectedLexemeCount: number;
  onClose: () => void;
  onCaptureCurrentSelection: () => void;
  onRemoveManualAnchor: (conceptKey: string) => void;
  onSubmitManualOffset: () => void;
  onApplyDetectedOffset: () => void;
  onOpenManualOffset: () => void;
  onOpenJobLogs: (jobId: string) => void;
}

function renderDetectedSummary(result: OffsetDetectResult) {
  const direction = result.direction ?? (result.offsetSec >= 0 ? 'later' : 'earlier');
  const sign = result.offsetSec >= 0 ? '+' : '';
  const lowConf = (result.confidence ?? 0) < 0.5;
  const directionWord =
    direction === 'later' ? 'later (toward the end)'
    : direction === 'earlier' ? 'earlier (toward the start)'
    : 'no-op (no shift)';
  const arrow = direction === 'later' ? '→' : direction === 'earlier' ? '←' : '·';
  const isManual = result.method === 'manual_pair';
  return { directionWord, sign, lowConf, arrow, isManual };
}

export function OffsetAdjustmentModal({
  open,
  offsetState,
  manualAnchors,
  manualConsensus,
  manualBusy,
  protectedLexemeCount,
  onClose,
  onCaptureCurrentSelection,
  onRemoveManualAnchor,
  onSubmitManualOffset,
  onApplyDetectedOffset,
  onOpenManualOffset,
  onOpenJobLogs,
}: OffsetAdjustmentModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Timestamp Offset"
      dismissible={offsetState.phase !== 'detecting' && offsetState.phase !== 'applying'}
    >
      <div className="space-y-3 text-sm" data-testid="offset-modal">
        {offsetState.phase === 'detecting' && (
          <div className="space-y-2" data-testid="offset-detecting">
            <div className="flex items-center gap-2 text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{offsetState.progressMessage ?? 'Detecting offset…'}</span>
              <span className="ml-auto font-mono text-[11px] tabular-nums text-slate-400">
                {Math.round(offsetState.progress)}%
              </span>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all"
                style={{ width: `${Math.max(2, Math.round(offsetState.progress))}%` }}
              />
            </div>
            <p className="text-[11px] text-slate-400">
              This window stays open while the worker is running. The header also mirrors the status.
            </p>
          </div>
        )}

        {offsetState.phase === 'manual' && (() => {
          const consensus = manualConsensus;
          const directionWord =
            !consensus
              ? null
              : consensus.median > 0.001
                ? 'later (toward the end)'
                : consensus.median < -0.001
                  ? 'earlier (toward the start)'
                  : 'no shift';
          const arrow =
            !consensus
              ? null
              : consensus.median > 0.001
                ? '→'
                : consensus.median < -0.001
                  ? '←'
                  : '·';
          const noisy = consensus !== null && consensus.mad > 2.0;
          return (
            <div className="space-y-3" data-testid="offset-manual">
              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                <p className="leading-snug">
                  Capture one trusted lexeme at a time. In Annotate, click a lexeme, scrub to where you actually hear it, then press
                  <span className="mx-1 inline-flex items-center gap-1 rounded bg-indigo-100 px-1.5 py-0.5 font-semibold text-indigo-700">
                    <Anchor className="h-3 w-3" />Anchor offset here
                  </span>
                  on the playback bar. Captured pairs accumulate below — adding more refines the offset.
                </p>
              </div>

              {manualAnchors.length === 0 ? (
                <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-slate-300 p-4 text-xs text-slate-500">
                  <Anchor className="h-5 w-5 text-slate-300" />
                  No anchors captured yet.
                  <span className="text-[11px] text-slate-400">
                    Switch to Annotate, select a lexeme, scrub the waveform, then click
                    <em> Anchor offset here</em>.
                  </span>
                </div>
              ) : (
                <ul className="space-y-1.5" data-testid="offset-manual-anchor-list">
                  {manualAnchors.map((anchor) => {
                    const pairOffset = anchor.audioTimeSec - anchor.csvTimeSec;
                    const disagrees = consensus !== null && Math.abs(pairOffset - consensus.median) > 1.5;
                    const sign = pairOffset >= 0 ? '+' : '';
                    return (
                      <li
                        key={anchor.conceptKey}
                        className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${disagrees ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`}
                        data-testid="offset-manual-anchor"
                      >
                        <div className="flex-1 truncate">
                          <span className="font-semibold text-slate-800">{anchor.conceptName}</span>
                          <span className="ml-1 font-mono text-slate-400">{anchor.conceptKey}</span>
                        </div>
                        <div className="font-mono text-[11px] text-slate-500 tabular-nums" title={`csv ${anchor.csvTimeSec.toFixed(3)}s → audio ${anchor.audioTimeSec.toFixed(3)}s`}>
                          {formatPlaybackTime(anchor.csvTimeSec)} <span className="text-slate-300">→</span> {formatPlaybackTime(anchor.audioTimeSec)}
                        </div>
                        <div className={`w-16 text-right font-mono text-[11px] tabular-nums ${disagrees ? 'text-rose-600' : 'text-slate-700'}`}>
                          {sign}{pairOffset.toFixed(2)}s
                        </div>
                        <button
                          onClick={() => onRemoveManualAnchor(anchor.conceptKey)}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-rose-600"
                          title="Remove this anchor"
                          data-testid={`offset-manual-anchor-remove-${anchor.conceptKey}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}

              {consensus !== null && (
                <div className={`rounded-md border p-3 text-xs ${noisy ? 'border-amber-300 bg-amber-50' : 'border-emerald-200 bg-emerald-50'}`}>
                  <div className="font-mono text-base text-slate-900" data-testid="offset-manual-consensus">
                    {consensus.median >= 0 ? '+' : ''}{consensus.median.toFixed(3)} s <span className="text-slate-400">{arrow}</span>
                  </div>
                  <div className="mt-1 text-slate-700">
                    Apply will move every tier interval for every concept in this speaker <strong>{Math.abs(consensus.median).toFixed(3)} s {directionWord}</strong>.
                  </div>
                  <div className="mt-1 text-slate-500">
                    {manualAnchors.length} anchor{manualAnchors.length === 1 ? '' : 's'}
                    {consensus.mad > 0 && <> · spread ±{consensus.mad.toFixed(2)}s</>}
                    {noisy && <> — anchors disagree, review the rose-highlighted ones above</>}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  onClick={onCaptureCurrentSelection}
                  title="Use the lexeme currently selected in the sidebar plus the current playback time"
                  data-testid="offset-manual-capture"
                >
                  <Plus className="h-3 w-3" /> Capture from current selection
                </button>
                <div className="flex gap-2">
                  <button
                    className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                    onClick={onClose}
                  >
                    Close
                  </button>
                  <button
                    className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    onClick={onSubmitManualOffset}
                    disabled={!manualAnchors.length || manualBusy}
                    data-testid="offset-manual-submit"
                  >
                    {manualBusy ? 'Computing…' : 'Review & apply →'}
                  </button>
                </div>
              </div>
            </div>
          );
        })()}

        {offsetState.phase === 'detected' && (() => {
          const summary = renderDetectedSummary(offsetState.result);
          const result = offsetState.result;
          return (
            <>
              <div className={`rounded-md border p-3 text-xs ${summary.lowConf ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-slate-50'}`}>
                <div className="font-mono text-base text-slate-900" data-testid="offset-value">
                  {summary.sign}{result.offsetSec.toFixed(3)} s <span className="text-slate-400">{summary.arrow}</span>
                </div>
                <div className="mt-1 text-slate-700" data-testid="offset-direction-label">
                  Apply will move every tier interval for every concept in this speaker <strong>{Math.abs(result.offsetSec).toFixed(3)} s {summary.directionWord}</strong>.
                </div>
                <div className="mt-2 text-slate-500">
                  {summary.isManual ? (
                    <>From single trusted pair · confidence {Math.round((result.confidence ?? 0) * 100)}%</>
                  ) : (
                    <>
                      Confidence {Math.round((result.confidence ?? 0) * 100)}% · {result.nAnchors}/{result.totalAnchors} anchors matched · {result.totalSegments} STT segments
                      {typeof result.spreadSec === 'number' && result.spreadSec > 0 && <> · spread ±{result.spreadSec.toFixed(2)}s</>}
                      {result.method && <> · {result.method.replace('_', ' ')}</>}
                    </>
                  )}
                </div>
              </div>
              {(result.warnings?.length ?? 0) > 0 && (
                <ul className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-900">
                  {result.warnings?.map((warning, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />{warning}
                    </li>
                  ))}
                </ul>
              )}
              {protectedLexemeCount > 0 && (
                <div
                  data-testid="offset-protected-notice"
                  className="flex items-start gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-[11px] text-emerald-900"
                >
                  <Anchor className="mt-0.5 h-3 w-3 flex-shrink-0" />
                  <span>
                    <strong>{protectedLexemeCount}</strong> lexeme{protectedLexemeCount === 1 ? '' : 's'} will be protected — you have manually adjusted {protectedLexemeCount === 1 ? 'its' : 'their'} timing and the offset will skip {protectedLexemeCount === 1 ? 'it' : 'them'}.
                  </span>
                </div>
              )}
              <div className="flex justify-between gap-2">
                <button
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  onClick={onOpenManualOffset}
                  data-testid="offset-use-known-anchor"
                >
                  Use a known anchor instead
                </button>
                <div className="flex gap-2">
                  <button
                    className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                    onClick={onClose}
                  >
                    Cancel
                  </button>
                  <button
                    className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 ${summary.lowConf ? 'bg-amber-600' : 'bg-indigo-600'}`}
                    onClick={onApplyDetectedOffset}
                    data-testid="offset-apply"
                    title={summary.lowConf ? 'Low confidence — review the matches before applying' : undefined}
                  >
                    {summary.lowConf ? 'Apply anyway' : 'Apply offset'}
                  </button>
                </div>
              </div>
            </>
          );
        })()}

        {offsetState.phase === 'applying' && (
          <div className="flex items-center gap-2 text-slate-600">
            <Loader2 className="h-4 w-4 animate-spin" /> Applying offset…
          </div>
        )}

        {offsetState.phase === 'applied' && (() => {
          const shiftedConcepts = offsetState.shiftedConcepts ?? offsetState.shifted;
          const conceptUnit = shiftedConcepts === 1 ? 'concept' : 'concepts';
          const intervalUnit = offsetState.shifted === 1 ? 'tier interval' : 'tier intervals';
          return (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-emerald-700">
                <CheckCircle2 className="h-4 w-4" /> Shifted {shiftedConcepts} {conceptUnit} ({offsetState.shifted} {intervalUnit}) by {offsetState.result.offsetSec.toFixed(3)}s
              </div>
              {offsetState.protected > 0 && (
                <div
                  data-testid="offset-applied-protected"
                  className="flex items-start gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-[11px] text-emerald-900"
                >
                  <Anchor className="mt-0.5 h-3 w-3 flex-shrink-0" />
                  <span>
                    Left <strong>{offsetState.protected}</strong> interval row{offsetState.protected === 1 ? '' : 's'} untouched — they were previously locked by manual timestamp edits or anchor captures.
                  </span>
                </div>
              )}
              <div className="flex justify-end">
                <button
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                  onClick={onClose}
                >
                  Close
                </button>
              </div>
            </div>
          );
        })()}

        {offsetState.phase === 'error' && (
          <div className="space-y-2">
            <div className="flex items-start gap-2 text-rose-700">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              <span data-testid="offset-error">{offsetState.message}</span>
            </div>
            {offsetState.jobId && (
              <div className="text-[11px] text-slate-500">
                Job <span className="font-mono text-slate-700">{offsetState.jobId}</span>
                {' — '}
                <button
                  className="font-semibold text-indigo-700 underline hover:text-indigo-800"
                  onClick={() => onOpenJobLogs(offsetState.jobId!)}
                  data-testid="offset-error-view-log"
                >
                  View crash log
                </button>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                onClick={onOpenManualOffset}
              >
                Try a known anchor
              </button>
              <button
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                onClick={onClose}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
