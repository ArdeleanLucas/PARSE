import React, { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash,
  Copy,
  RotateCw,
  SkipForward,
  XCircle,
} from "lucide-react";
import type { PipelineStepResultBase } from "../../api/client";
import {
  classifyCell,
  okDetail,
  truncate,
  type BatchSpeakerOutcome,
  type PipelineStepId,
} from "./batchReportShared";

function DetailsBlock({
  speaker,
  step,
  error,
  traceback,
}: {
  speaker: string;
  step: string;
  error: string;
  traceback: string | null;
}) {
  const [copied, setCopied] = useState(false);
  const body = traceback && traceback.trim() ? traceback : error;

  const onCopy = () => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        navigator.clipboard.writeText(body).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          },
          () => {
            /* ignore */
          },
        );
      }
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      role="region"
      aria-label={`Traceback for ${speaker} ${step}`}
      className="mt-1 rounded border border-rose-200 bg-rose-50/60 p-2"
    >
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wide text-rose-700">
          Full error {traceback ? "+ traceback" : ""}
        </div>
        <button
          type="button"
          aria-label="Copy traceback to clipboard"
          onClick={onCopy}
          className="inline-flex items-center gap-1 rounded border border-rose-200 bg-white px-1.5 py-0.5 text-[10px] text-rose-700 hover:bg-rose-100"
        >
          <Copy className="h-3 w-3" />
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="max-h-[200px] overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 font-mono text-[11px] leading-snug text-rose-900">
        {error}
        {traceback && traceback.trim() ? `\n\n${traceback}` : ""}
      </pre>
    </div>
  );
}

function StepCell({
  outcome,
  step,
  stepInBatch,
  isOpen,
  onToggle,
}: {
  outcome: BatchSpeakerOutcome;
  step: PipelineStepId;
  stepInBatch: boolean;
  isOpen: boolean;
  onToggle: () => void;
}) {
  if (!stepInBatch) {
    return (
      <td
        className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300"
        title="Step was not selected for this batch"
      >
        —
      </td>
    );
  }
  if (!outcome.result) {
    return (
      <td
        className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300"
        title="Speaker-level error — see the highlighted row below for details"
      >
        —
      </td>
    );
  }
  const cell = outcome.result.results[step];
  if (!cell) {
    return (
      <td
        className="border-b border-slate-100 px-2 py-1.5 align-top"
        title={`Backend returned no result entry for "${step}". Inspect via Download report.`}
      >
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
          <SkipForward className="h-3.5 w-3.5" /> No data
        </span>
      </td>
    );
  }

  const kind = classifyCell(cell);

  if (kind === "ok") {
    return (
      <td className="border-b border-slate-100 bg-emerald-50/40 px-2 py-1.5 align-top">
        <div className="flex items-center gap-1.5 text-emerald-700">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span className="text-xs font-semibold">OK</span>
          <span className="text-[11px] text-emerald-900/70 tabular-nums">
            {okDetail(step, cell)}
          </span>
        </div>
      </td>
    );
  }

  if (kind === "skipped") {
    const reason =
      (typeof cell.reason === "string" && cell.reason) ||
      (typeof cell["message"] === "string" ? (cell["message"] as string) : "") ||
      "Nothing to do";
    return (
      <td className="border-b border-slate-100 bg-slate-50 px-2 py-1.5 align-top">
        <div className="flex items-center gap-1.5 text-slate-600" title={reason}>
          <SkipForward className="h-4 w-4 shrink-0" />
          <span className="text-xs font-semibold">Skipped</span>
          {reason && <span className="text-[11px] text-slate-500">{truncate(reason)}</span>}
        </div>
      </td>
    );
  }

  if (kind === "empty") {
    const filled = typeof cell.filled === "number" ? cell.filled : 0;
    const total = typeof cell.total === "number" ? cell.total : 0;
    const breakdown = cell.skip_breakdown ?? null;
    const samples = Array.isArray(cell.exception_samples)
      ? (cell.exception_samples as unknown[]).filter(
          (s): s is string => typeof s === "string" && s.length > 0,
        )
      : [];
    const hasDetails =
      samples.length > 0 ||
      (breakdown && Object.values(breakdown).some((v) => typeof v === "number" && v > 0));

    return (
      <td className="border-b border-slate-100 bg-amber-50/60 px-2 py-1.5 align-top">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5 text-amber-800">
            <CircleSlash className="h-3.5 w-3.5 shrink-0" />
            <span className="text-xs font-semibold">Empty</span>
            <span className="text-[11px] text-amber-900/80 tabular-nums">{filled}/{total} written</span>
          </div>
          {hasDetails && (
            <>
              <button
                type="button"
                onClick={onToggle}
                className="inline-flex w-fit items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-amber-800 hover:bg-amber-100"
                aria-expanded={isOpen}
              >
                {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                Why
              </button>
              {isOpen && (
                <div
                  role="region"
                  aria-label={`Empty-step details for ${outcome.speaker} ${step}`}
                  className="mt-1 rounded border border-amber-200 bg-white p-2 text-[11px] text-amber-900"
                >
                  {breakdown && (
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                      {Object.entries(breakdown)
                        .filter(([, v]) => typeof v === "number" && v > 0)
                        .map(([k, v]) => (
                          <React.Fragment key={k}>
                            <dt className="font-mono text-amber-800/80">{k}</dt>
                            <dd className="text-right font-mono tabular-nums">{String(v)}</dd>
                          </React.Fragment>
                        ))}
                    </dl>
                  )}
                  {samples.length > 0 && (
                    <pre className="mt-1 max-h-[160px] overflow-auto whitespace-pre-wrap break-words rounded bg-amber-50 p-1.5 font-mono text-[10.5px] leading-snug text-amber-900">
                      {samples.join("\n")}
                    </pre>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </td>
    );
  }

  if (kind === "unknown") {
    const keys = Object.keys(cell).join(", ");
    return (
      <td
        className="border-b border-slate-100 bg-slate-50 px-2 py-1.5 align-top"
        title={`Step ran but returned an unfamiliar shape. Keys: ${keys}. Use Download report to inspect.`}
      >
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
          <SkipForward className="h-4 w-4" /> Ran (unclassified)
        </span>
      </td>
    );
  }

  const shortError = (cell as PipelineStepResultBase).error ?? "Error";
  const traceback = typeof cell.traceback === "string" && cell.traceback.trim() ? cell.traceback : null;
  return (
    <td className="border-b border-slate-100 px-2 py-1.5 align-top">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1 text-rose-700">
          <XCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="text-xs font-medium">Error</span>
          <span className="font-mono text-[11px] text-rose-900/80" title={shortError}>
            {truncate(shortError)}
          </span>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex w-fit items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-rose-700 hover:bg-rose-100"
          aria-expanded={isOpen}
        >
          {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Details
        </button>
        {isOpen && (
          <DetailsBlock
            speaker={outcome.speaker}
            step={step}
            error={shortError}
            traceback={traceback}
          />
        )}
      </div>
    </td>
  );
}

function SpeakerStatusCell({ outcome }: { outcome: BatchSpeakerOutcome }) {
  if (outcome.status === "complete") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5" /> complete
        </span>
      </td>
    );
  }
  if (outcome.status === "error") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-rose-700" title={outcome.error ?? undefined}>
          <XCircle className="h-3.5 w-3.5" /> errored
          {outcome.error && (
            <span className="font-mono text-[11px] text-rose-900/80">({truncate(outcome.error, 30)})</span>
          )}
        </span>
      </td>
    );
  }
  if (outcome.status === "running") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-indigo-700">
          <RotateCw className="h-3.5 w-3.5 animate-spin" /> running
        </span>
      </td>
    );
  }
  if (outcome.status === "cancelled") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <span className="inline-flex items-center gap-1 text-xs text-amber-700">
          <SkipForward className="h-3.5 w-3.5" /> cancelled
        </span>
      </td>
    );
  }
  return (
    <td className="border-b border-slate-100 px-2 py-1.5 align-top">
      <span className="inline-flex items-center gap-1 text-xs text-slate-500">pending</span>
    </td>
  );
}

function SpeakerErrorBanner({
  outcome,
  columnCount,
  isOpen,
  onToggle,
}: {
  outcome: BatchSpeakerOutcome;
  columnCount: number;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const hasTraceback = outcome.error != null && /traceback/i.test(outcome.error);
  const lostContactAfterStart = outcome.errorPhase === "poll" && !!outcome.jobId;

  return (
    <tr>
      <td colSpan={columnCount} className="border-b border-amber-200 bg-amber-50 px-3 py-2">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-amber-900">
              {lostContactAfterStart ? "Lost contact after start:" : "Speaker-level error:"}
            </span>
            <span className="font-mono text-[11px] text-amber-900/90">{outcome.error ?? "(no message)"}</span>
            {lostContactAfterStart && outcome.jobId && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] text-amber-900">
                job {outcome.jobId}
              </span>
            )}
            {hasTraceback && (
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={isOpen}
                className="ml-auto inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-amber-800 hover:bg-amber-100"
              >
                {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                Details
              </button>
            )}
          </div>
          {lostContactAfterStart && (
            <div className="text-[11px] text-amber-900/80">
              The pipeline job was created, but the client lost `/api` connectivity while polling. Reattach or reconcile by backend job id before treating this as a true speaker failure.
            </div>
          )}
          {hasTraceback && isOpen && (
            <DetailsBlock
              speaker={outcome.speaker}
              step="speaker"
              error={outcome.error ?? ""}
              traceback={outcome.error ?? null}
            />
          )}
        </div>
      </td>
    </tr>
  );
}

export function BatchReportTableRow({
  outcome,
  stepsRun,
  columnCount,
  isCellOpen,
  onToggleCell,
  isBannerOpen,
  onToggleBanner,
}: {
  outcome: BatchSpeakerOutcome;
  stepsRun: PipelineStepId[];
  columnCount: number;
  isCellOpen: (step: PipelineStepId) => boolean;
  onToggleCell: (step: PipelineStepId) => void;
  isBannerOpen: boolean;
  onToggleBanner: () => void;
}) {
  const isWholeSpeakerError = outcome.status === "error" && outcome.result === null;

  return (
    <React.Fragment>
      <tr data-testid={`batch-report-row-${outcome.speaker}`}>
        <td className="border-b border-slate-100 px-3 py-1.5 align-top font-medium text-slate-800">
          {outcome.speaker}
        </td>
        {stepsRun.map((step) => (
          <StepCell
            key={step}
            outcome={outcome}
            step={step}
            stepInBatch={true}
            isOpen={isCellOpen(step)}
            onToggle={() => onToggleCell(step)}
          />
        ))}
        <SpeakerStatusCell outcome={outcome} />
      </tr>
      {isWholeSpeakerError && (
        <SpeakerErrorBanner
          outcome={outcome}
          columnCount={columnCount}
          isOpen={isBannerOpen}
          onToggle={onToggleBanner}
        />
      )}
    </React.Fragment>
  );
}
