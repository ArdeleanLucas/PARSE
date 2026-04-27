import { AlertCircle, CheckCircle2, Download, Filter, Play, RefreshCw, Save, Upload } from 'lucide-react';

import { formatEta } from '../../../hooks/useActionJob';
import { isCompareComputeMode, isCompareRunDisabled } from '../compareComputeContract';
import { tagFilterOptions } from './shared';
import type { RightPanelProps } from './types';

type CompareTabContentProps = Pick<
  RightPanelProps,
  | 'selectedSpeakers'
  | 'conceptCount'
  | 'speakers'
  | 'computeMode'
  | 'onComputeModeChange'
  | 'onComputeRun'
  | 'crossSpeakerJobStatus'
  | 'computeJobStatus'
  | 'computeJobProgress'
  | 'computeJobEtaMs'
  | 'computeJobError'
  | 'clefConfigured'
  | 'onOpenSourcesReport'
  | 'onOpenClefConfig'
  | 'onRefreshEnrichments'
  | 'tagFilter'
  | 'onTagFilterChange'
  | 'onOpenLoadDecisions'
  | 'onSaveDecisions'
  | 'onExportLingPy'
  | 'exporting'
  | 'onOpenCommentsImport'
>;

export function CompareTabContent({
  selectedSpeakers,
  conceptCount,
  speakers,
  computeMode,
  onComputeModeChange,
  onComputeRun,
  crossSpeakerJobStatus,
  computeJobStatus,
  computeJobProgress,
  computeJobEtaMs,
  computeJobError,
  clefConfigured,
  onOpenSourcesReport,
  onOpenClefConfig,
  onRefreshEnrichments,
  tagFilter,
  onTagFilterChange,
  onOpenLoadDecisions,
  onSaveDecisions,
  onExportLingPy,
  exporting,
  onOpenCommentsImport,
}: CompareTabContentProps) {
  return (
    <>
      <div className="border-b border-slate-100 p-4">
        <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Compute</h4>
        <select
          value={computeMode}
          onChange={(event) => {
            const nextMode = event.target.value;
            if (isCompareComputeMode(nextMode)) {
              onComputeModeChange(nextMode);
            }
          }}
          className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none"
        >
          <option value="cognates">Cognates</option>
          <option value="similarity">Phonetic similarity</option>
          <option value="contact-lexemes">Borrowing detection (CLEF)</option>
        </select>
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button
            className="inline-flex items-center justify-center gap-1 rounded-md bg-indigo-600 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            onClick={onComputeRun}
            disabled={isCompareRunDisabled({
              computeMode,
              selectedSpeakersCount: selectedSpeakers.length,
              crossSpeakerJobStatus,
              computeJobStatus,
            })}
          >
            <Play className="h-3 w-3" /> Run
          </button>
          <button
            className="inline-flex items-center justify-center gap-1 rounded-md border border-slate-200 bg-white py-1.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
            onClick={onRefreshEnrichments}
          >
            <RefreshCw className="h-3 w-3" /> Refresh
          </button>
        </div>
        {computeMode === 'contact-lexemes' && (
          <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px]">
            <span className={clefConfigured ? 'text-emerald-700' : 'text-amber-700'}>
              {clefConfigured === null
                ? 'Checking CLEF config…'
                : clefConfigured
                  ? 'CLEF configured'
                  : 'CLEF not configured — Run will open setup'}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={onOpenSourcesReport}
                data-testid="clef-sources-report-open"
                className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-100"
                title="Show which providers contributed each reference form (for citation)"
              >
                Sources Report
              </button>
              <button
                onClick={onOpenClefConfig}
                className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600 hover:bg-slate-100"
              >
                Configure
              </button>
            </div>
          </div>
        )}
        {computeMode !== 'contact-lexemes' && computeJobStatus === 'running' && (
          <div className="mt-1 text-[10px] text-indigo-600">
            Running… {Math.round(computeJobProgress * 100)}%
            {computeJobEtaMs !== null && computeJobEtaMs > 0 && (
              <span className="text-slate-400"> · ~{formatEta(computeJobEtaMs)} left</span>
            )}
          </div>
        )}
        {computeMode !== 'contact-lexemes' && computeJobStatus === 'error' && (
          <div className="mt-1 text-[10px] text-rose-600">{computeJobError}</div>
        )}
      </div>

      <div className="border-b border-slate-100 p-4">
        <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Status</h4>
        <div className="mb-2 flex items-center gap-2">
          {speakers.length > 0 || conceptCount > 0 ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
              <span className="text-[11px] font-semibold text-slate-700">project.json</span>
              <span className="ml-auto text-[10px] text-slate-400">loaded</span>
            </>
          ) : (
            <>
              <AlertCircle className="h-3.5 w-3.5 text-amber-500" />
              <span className="text-[11px] font-semibold text-slate-700">Workspace empty</span>
            </>
          )}
        </div>
        {speakers.length === 0 && conceptCount === 0 ? (
          <div className="rounded-md bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
            No speakers or concepts imported yet. Use <span className="font-semibold">Import</span> to add data to this workspace.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded-md bg-slate-50 px-2 py-1.5">
              <div className="font-mono text-sm font-semibold text-slate-900">{speakers.length}</div>
              <div className="text-[9px] uppercase tracking-wider text-slate-400">speakers</div>
            </div>
            <div className="rounded-md bg-slate-50 px-2 py-1.5">
              <div className="font-mono text-sm font-semibold text-slate-900">{conceptCount}</div>
              <div className="text-[9px] uppercase tracking-wider text-slate-400">concepts</div>
            </div>
          </div>
        )}
      </div>

      <div className="border-b border-slate-100 p-4">
        <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          <Filter className="h-3 w-3" /> Filter by tag
        </h4>
        <div className="space-y-1">
          {tagFilterOptions.map(({ key, label, dot }) => (
            <button
              key={key}
              onClick={() => onTagFilterChange(key)}
              className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-[11px] transition ${tagFilter === key ? 'bg-indigo-50 font-semibold text-indigo-800' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4">
        <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Decisions</h4>
        <div className="space-y-1.5">
          <button
            className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            onClick={onOpenLoadDecisions}
          >
            <Upload className="h-3 w-3" /> Load decisions
          </button>
          <button
            className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
            onClick={onSaveDecisions}
          >
            <Save className="h-3 w-3" /> Save decisions
          </button>
          <button
            className="flex w-full items-center gap-2 rounded-md bg-indigo-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            onClick={onExportLingPy}
            disabled={exporting}
          >
            <Download className="h-3 w-3" />
            {exporting ? 'Exporting…' : 'Export LingPy TSV'}
          </button>
          <button
            data-testid="open-comments-import"
            onClick={onOpenCommentsImport}
            className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
          >
            <Upload className="h-3 w-3" /> Import Audition comments
          </button>
        </div>
      </div>
    </>
  );
}
