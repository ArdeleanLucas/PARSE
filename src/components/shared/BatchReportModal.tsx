import React, { useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  RotateCw,
  SkipForward,
  XCircle,
} from "lucide-react";
import { Modal } from "./Modal";
import type { PipelineRunResult, PipelineStepResultBase } from "../../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export interface BatchSpeakerOutcome {
  speaker: string;
  /** "cancelled" means the user cancelled the batch before this speaker ran.
   *  The speaker's pipeline never started server-side; its result is null. */
  status: "pending" | "running" | "complete" | "error" | "cancelled";
  /** Whole-speaker error (e.g. network failure before the pipeline job even started). */
  error: string | null;
  result: PipelineRunResult | null;
}

export interface BatchReportModalProps {
  open: boolean;
  onClose: () => void;
  outcomes: BatchSpeakerOutcome[];
  stepsRun: PipelineStepId[];
  onRerunFailed?: (speakers: string[]) => void;
}

const STEP_LABELS: Record<PipelineStepId, string> = {
  normalize: "Normalize",
  stt: "STT",
  ortho: "Ortho",
  ipa: "IPA",
};

const TRUNCATE_LEN = 40;

function truncate(text: string, max: number = TRUNCATE_LEN): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 1)) + "…";
}

function okDetail(step: PipelineStepId, cell: PipelineStepResultBase): string {
  switch (step) {
    case "normalize":
      return "done";
    case "stt": {
      const segs = cell["segments"];
      if (typeof segs === "number") return `${segs} segs`;
      return "done";
    }
    case "ortho":
    case "ipa": {
      const ivs = cell["intervals"];
      if (typeof ivs === "number") return `${ivs} ivs`;
      return "done";
    }
  }
}

function speakerHasFailure(outcome: BatchSpeakerOutcome): boolean {
  if (outcome.status === "error") return true;
  if (outcome.result) {
    for (const step of Object.keys(outcome.result.results) as PipelineStepId[]) {
      const cell = outcome.result.results[step];
      if (cell && cell.status === "error") return true;
    }
  }
  return false;
}

function countTotals(
  outcomes: BatchSpeakerOutcome[],
  stepsRun: PipelineStepId[],
): { ok: number; skipped: number; errored: number } {
  let ok = 0;
  let skipped = 0;
  let errored = 0;
  for (const outcome of outcomes) {
    if (outcome.status === "error" && !outcome.result) {
      // Whole-speaker error counts as one errored "cell" so it shows up in totals.
      errored += 1;
      continue;
    }
    if (!outcome.result) continue;
    for (const step of stepsRun) {
      const cell = outcome.result.results[step];
      if (!cell) continue;
      if (cell.status === "ok") ok += 1;
      else if (cell.status === "skipped") skipped += 1;
      else if (cell.status === "error") errored += 1;
    }
  }
  return { ok, skipped, errored };
}

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
      <pre
        className="max-h-[200px] overflow-auto whitespace-pre-wrap break-words rounded bg-white p-2 font-mono text-[11px] leading-snug text-rose-900"
      >
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
      <td className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300">
        —
      </td>
    );
  }
  // Whole-speaker errors (no result) are handled by a banner row — for each
  // individual step cell in that row we render a dim dash.
  if (!outcome.result) {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300">
        —
      </td>
    );
  }
  const cell = outcome.result.results[step];
  if (!cell) {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 text-center text-slate-300">
        —
      </td>
    );
  }

  if (cell.status === "ok") {
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <div className="flex items-center gap-1 text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
          <span className="text-xs font-medium">OK</span>
          <span className="text-[11px] text-emerald-900/70">
            {okDetail(step, cell)}
          </span>
        </div>
      </td>
    );
  }

  if (cell.status === "skipped") {
    const reason = cell.reason ?? "";
    return (
      <td className="border-b border-slate-100 px-2 py-1.5 align-top">
        <div
          className="flex items-center gap-1 text-slate-600"
          title={reason || undefined}
        >
          <SkipForward className="h-3.5 w-3.5 shrink-0" />
          <span className="text-xs font-medium">Skipped</span>
          {reason && (
            <span className="text-[11px] text-slate-500">
              {truncate(reason)}
            </span>
          )}
        </div>
      </td>
    );
  }

  // cell.status === "error"
  const shortError = cell.error ?? "Error";
  const traceback =
    typeof cell.traceback === "string" && cell.traceback.trim()
      ? cell.traceback
      : null;
  return (
    <td className="border-b border-slate-100 px-2 py-1.5 align-top">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1 text-rose-700">
          <XCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="text-xs font-medium">Error</span>
          <span
            className="font-mono text-[11px] text-rose-900/80"
            title={shortError}
          >
            {truncate(shortError)}
          </span>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex w-fit items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-rose-700 hover:bg-rose-100"
          aria-expanded={isOpen}
        >
          {isOpen ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
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
        <span
          className="inline-flex items-center gap-1 text-xs text-rose-700"
          title={outcome.error ?? undefined}
        >
          <XCircle className="h-3.5 w-3.5" /> errored
          {outcome.error && (
            <span className="font-mono text-[11px] text-rose-900/80">
              ({truncate(outcome.error, 30)})
            </span>
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
  // pending
  return (
    <td className="border-b border-slate-100 px-2 py-1.5 align-top">
      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
        pending
      </span>
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
  // Crude traceback detection: if the error text contains "Traceback" keyword,
  // we surface a details expand. Most network errors won't have one — in that
  // case we just show the error message and skip the expand button.
  const hasTraceback =
    outcome.error != null && /traceback/i.test(outcome.error);

  return (
    <tr>
      <td
        colSpan={columnCount}
        className="border-b border-amber-200 bg-amber-50 px-3 py-2"
      >
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-amber-900">
              Speaker-level error:
            </span>
            <span className="font-mono text-[11px] text-amber-900/90">
              {outcome.error ?? "(no message)"}
            </span>
            {hasTraceback && (
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={isOpen}
                className="ml-auto inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[11px] text-amber-800 hover:bg-amber-100"
              >
                {isOpen ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                Details
              </button>
            )}
          </div>
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

export function BatchReportModal({
  open,
  onClose,
  outcomes,
  stepsRun,
  onRerunFailed,
}: BatchReportModalProps): JSX.Element | null {
  const [openCells, setOpenCells] = useState<Set<string>>(new Set());
  const [openBanners, setOpenBanners] = useState<Set<string>>(new Set());

  const totals = useMemo(
    () => countTotals(outcomes, stepsRun),
    [outcomes, stepsRun],
  );
  const failedSpeakers = useMemo(
    () => outcomes.filter(speakerHasFailure).map((o) => o.speaker),
    [outcomes],
  );

  const toggleCell = (speaker: string, step: string) => {
    setOpenCells((prev) => {
      const next = new Set(prev);
      const key = `${speaker}:${step}`;
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleBanner = (speaker: string) => {
    setOpenBanners((prev) => {
      const next = new Set(prev);
      if (next.has(speaker)) next.delete(speaker);
      else next.add(speaker);
      return next;
    });
  };

  const handleDownload = () => {
    const payload = {
      generated_at: new Date().toISOString(),
      steps_run: stepsRun,
      outcomes,
    };
    const json = JSON.stringify(payload, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `parse-batch-report-${new Date().toISOString()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleRerun = () => {
    if (onRerunFailed && failedSpeakers.length > 0) {
      onRerunFailed(failedSpeakers);
    }
  };

  const columnCount = stepsRun.length + 2; // speaker col + steps + trailing status col
  const allClean = totals.errored === 0 && totals.skipped === 0;

  const title = `Batch Report — ${outcomes.length} speakers × ${stepsRun.length} steps`;

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div
        className="flex w-[min(90vw,64rem)] flex-col gap-3"
        data-testid="batch-report-modal"
      >
        {/* Summary chips */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span
            className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800"
            data-testid="batch-report-chip-ok"
          >
            <CheckCircle2 className="h-3 w-3" />
            {totals.ok} ok
          </span>
          <span
            className="inline-flex items-center gap-1 rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-700"
            data-testid="batch-report-chip-skipped"
          >
            <SkipForward className="h-3 w-3" />
            {totals.skipped} skipped
          </span>
          <span
            className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-800"
            data-testid="batch-report-chip-errored"
          >
            <XCircle className="h-3 w-3" />
            {totals.errored} errored
          </span>
        </div>

        {stepsRun.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-500">
            No steps were run.
          </div>
        ) : (
          <>
            {allClean && outcomes.length > 0 && (
              <div
                className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
                data-testid="batch-report-all-clean"
              >
                All {outcomes.length} speaker
                {outcomes.length === 1 ? "" : "s"} processed cleanly.
              </div>
            )}

            <div className="max-h-[60vh] overflow-auto rounded border border-slate-200">
              <table
                className="min-w-full border-collapse text-left text-xs"
                data-testid="batch-report-table"
              >
                <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-600">
                  <tr>
                    <th className="border-b border-slate-200 px-3 py-2 font-semibold">
                      Speaker
                    </th>
                    {stepsRun.map((step) => (
                      <th
                        key={step}
                        className="border-b border-slate-200 px-2 py-2 font-semibold"
                      >
                        {STEP_LABELS[step]}
                      </th>
                    ))}
                    <th className="border-b border-slate-200 px-2 py-2 font-semibold">
                      Speaker status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {outcomes.map((outcome) => {
                    const isWholeSpeakerError =
                      outcome.status === "error" && outcome.result === null;
                    return (
                      <React.Fragment key={outcome.speaker}>
                        <tr data-testid={`batch-report-row-${outcome.speaker}`}>
                          <td className="border-b border-slate-100 px-3 py-1.5 align-top font-medium text-slate-800">
                            {outcome.speaker}
                          </td>
                          {stepsRun.map((step) => {
                            const key = `${outcome.speaker}:${step}`;
                            return (
                              <StepCell
                                key={step}
                                outcome={outcome}
                                step={step}
                                stepInBatch={true}
                                isOpen={openCells.has(key)}
                                onToggle={() =>
                                  toggleCell(outcome.speaker, step)
                                }
                              />
                            );
                          })}
                          <SpeakerStatusCell outcome={outcome} />
                        </tr>
                        {isWholeSpeakerError && (
                          <SpeakerErrorBanner
                            outcome={outcome}
                            columnCount={columnCount}
                            isOpen={openBanners.has(outcome.speaker)}
                            onToggle={() => toggleBanner(outcome.speaker)}
                          />
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* Footer */}
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={handleDownload}
            data-testid="batch-report-download"
            className="inline-flex items-center gap-1.5 rounded border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <Download className="h-3.5 w-3.5" />
            Download report (JSON)
          </button>
          <div className="flex items-center gap-2">
            {onRerunFailed && (
              <button
                type="button"
                onClick={handleRerun}
                disabled={failedSpeakers.length === 0}
                data-testid="batch-report-rerun-failed"
                className="inline-flex items-center gap-1.5 rounded bg-rose-600 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RotateCw className="h-3.5 w-3.5" />
                Rerun failed ({failedSpeakers.length})
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              data-testid="batch-report-close"
              className="rounded px-3 py-1 text-xs text-slate-600 hover:bg-slate-100"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
