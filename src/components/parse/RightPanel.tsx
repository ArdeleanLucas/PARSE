import {
  Activity,
  AlertCircle,
  Anchor,
  AudioLines,
  Check,
  CheckCircle2,
  Cpu,
  Database,
  Download,
  Filter,
  Layers,
  Mic,
  PanelRightClose,
  Play,
  Plus,
  RefreshCw,
  Save,
  Scissors,
  SlidersHorizontal,
  Upload,
  Users as UsersIcon,
  Video,
  X,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { formatEta } from '../../hooks/useActionJob';

type AppMode = 'annotate' | 'compare' | 'tags';

type CompareTagFilter = 'all' | 'untagged' | 'review' | 'confirmed' | 'problematic' | string;

type ComputeMode = 'cognates' | 'similarity' | 'contact-lexemes' | string;

type JobStatus = 'idle' | 'running' | 'complete' | 'error' | string;

type OffsetPhase = 'idle' | 'manual' | 'detecting' | 'ready' | 'applying' | string;

interface RightPanelProps {
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
  computeMode: ComputeMode;
  onComputeModeChange: (mode: string) => void;
  onComputeRun: () => void;
  crossSpeakerJobStatus: JobStatus;
  computeJobStatus: JobStatus;
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

export function RightPanel({
  panelOpen,
  onTogglePanel,
  currentMode,
  selectedSpeakers,
  speakers,
  conceptCount,
  speakerPicker,
  onSpeakerSelect,
  onAddSpeaker,
  onToggleSpeaker,
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
  activeActionSpeaker,
  offsetPhase,
  onDetectOffset,
  onOpenManualOffset,
  annotateSpeakerTools,
  annotateAuxTools,
  onSaveAnnotations,
}: RightPanelProps) {
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
        {[
          { icon: Database, label: 'Project' },
          { icon: UsersIcon, label: 'Speakers' },
          { icon: Cpu, label: 'Compute' },
          { icon: Filter, label: 'Filters' },
          { icon: Save, label: 'Decisions' },
        ].map(({ icon: Icon, label }) => (
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

      <div className={`h-[calc(100%-46px)] overflow-y-auto overflow-x-hidden transition-opacity duration-300 ${panelOpen ? 'opacity-100 delay-200' : 'pointer-events-none opacity-0'}`} style={{ width: 250 }}>
        <div className="border-b border-slate-100 p-4">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Speakers {currentMode === 'annotate' && <span className="ml-1 rounded bg-indigo-50 px-1 py-0.5 font-mono text-[8px] text-indigo-600">SINGLE</span>}
            </h4>
            <span className="text-[10px] text-slate-400">
              {currentMode === 'annotate' ? '1' : selectedSpeakers.length} / {speakers.length}
            </span>
          </div>
          <div className="mb-2 flex gap-1">
            <select
              value={currentMode === 'annotate' ? (selectedSpeakers[0] ?? '') : (speakerPicker ?? '')}
              onChange={(e) => onSpeakerSelect(e.target.value)}
              className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 focus:border-indigo-300 focus:outline-none"
            >
              {speakers.map((speaker) => <option key={speaker}>{speaker}</option>)}
            </select>
            {currentMode === 'compare' && (
              <button
                onClick={onAddSpeaker}
                data-testid="add-speaker-button"
                aria-label="Add speaker"
                className="grid h-6 w-6 place-items-center rounded-md bg-slate-900 text-white hover:bg-slate-700"
              >
                <Plus className="h-3 w-3" />
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {speakers.map((speaker) => {
              const active = currentMode === 'annotate' ? selectedSpeakers[0] === speaker : selectedSpeakers.includes(speaker);
              return (
                <button
                  key={speaker}
                  onClick={() => onToggleSpeaker(speaker)}
                  className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10px] transition ${active ? 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200' : 'bg-slate-50 text-slate-400 ring-1 ring-slate-100 hover:text-slate-600'}`}
                >
                  {speaker}
                  {active && currentMode === 'compare' && <X className="h-2.5 w-2.5" />}
                  {active && currentMode === 'annotate' && <Check className="h-2.5 w-2.5" />}
                </button>
              );
            })}
          </div>
          {currentMode === 'annotate' && (
            <p className="mt-2 text-[10px] leading-snug text-slate-400">
              Concept list scoped to <span className="font-mono text-slate-600">{selectedSpeakers[0]}</span>'s dataset.
            </p>
          )}
        </div>

        {currentMode === 'compare' ? (
          <>
            <div className="border-b border-slate-100 p-4">
              <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Compute</h4>
              <select
                value={computeMode}
                onChange={(e) => onComputeModeChange(e.target.value)}
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
                  disabled={
                    computeMode === 'contact-lexemes'
                      ? crossSpeakerJobStatus === 'running'
                      : computeJobStatus === 'running' || selectedSpeakers.length === 0
                  }
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
              {computeMode !== 'contact-lexemes' && (
                <div
                  className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 text-[10px] leading-snug text-slate-500"
                  data-testid="compare-compute-semantics"
                >
                  <div>Selected speakers only: {selectedSpeakers.length} of {speakers.length}.</div>
                  {computeMode === 'similarity' ? (
                    <div>Similarity currently uses the same shared backend recompute path as Cognates.</div>
                  ) : (
                    <div>Cognates recomputes cognate sets and similarity scores for the selected speaker subset.</div>
                  )}
                  <div>Refresh reloads saved enrichments only.</div>
                </div>
              )}
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
                {([
                  ['all', 'All concepts', 'bg-slate-400'],
                  ['untagged', 'Untagged', 'bg-slate-300'],
                  ['review', 'Review needed', 'bg-amber-400'],
                  ['confirmed', 'Confirmed', 'bg-emerald-500'],
                  ['problematic', 'Problematic', 'bg-rose-500'],
                ] as const).map(([key, label, dot]) => (
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
        ) : (
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
                  disabled={!activeActionSpeaker || offsetPhase === 'detecting' || offsetPhase === 'applying'}
                  data-testid="drawer-detect-offset"
                  className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Anchor className="h-3 w-3 text-slate-400" />
                  {offsetPhase === 'detecting' ? 'Detecting offset…' : 'Detect Timestamp Offset'}
                </button>
                <button
                  onClick={onOpenManualOffset}
                  disabled={!activeActionSpeaker || offsetPhase === 'detecting' || offsetPhase === 'applying'}
                  data-testid="drawer-detect-offset-manual"
                  title="Skip auto-detect and anchor the offset from captured lexeme pairs directly."
                  className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-left text-[11px] font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Anchor className="h-3 w-3 text-slate-400" />
                  Detect offset (manual anchors)
                </button>
              </div>
            </div>

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
                {([
                  { icon: AudioLines, label: 'Waveform view', hint: 'Segment-aware' },
                  { icon: Video, label: 'Video clip', hint: 'Synced to timeline' },
                  { icon: Scissors, label: 'Segment controls', hint: 'Split · Trim · Join' },
                  { icon: SlidersHorizontal, label: 'Formant tracker', hint: 'Praat-compatible' },
                  { icon: Mic, label: 'Re-record utterance', hint: 'Overlay on segment' },
                ] as const).map(({ icon: Icon, label, hint }) => (
                  <button key={label} className="group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-slate-50">
                    <Icon className="h-3.5 w-3.5 text-slate-400 group-hover:text-indigo-600" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] font-medium text-slate-700 truncate">{label}</div>
                      <div className="text-[9px] text-slate-400 truncate">{hint}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="border-b border-slate-100 p-4">
              <h4 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                <Filter className="h-3 w-3" /> Filter concepts
              </h4>
              <div className="space-y-1">
                {([
                  ['all', 'All concepts', 'bg-slate-400'],
                  ['untagged', 'Untagged', 'bg-slate-300'],
                  ['review', 'Review needed', 'bg-amber-400'],
                  ['confirmed', 'Confirmed', 'bg-emerald-500'],
                  ['problematic', 'Problematic', 'bg-rose-500'],
                ] as const).map(([key, label, dot]) => (
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
              <button
                className="flex w-full items-center gap-2 rounded-md bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700"
                onClick={onSaveAnnotations}
              >
                <Save className="h-3 w-3" /> Save annotations
              </button>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
