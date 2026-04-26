import { useMemo, useState } from "react";
import { Download, RotateCw } from "lucide-react";
import { BatchReportSummaryHeader } from "./BatchReportSummaryHeader";
import { BatchReportTableRow } from "./BatchReportTableRow";
import { Modal } from "./Modal";
import {
  STEP_LABELS,
  countTotals,
  speakerHasFailure,
  type BatchSpeakerOutcome,
  type PipelineStepId,
} from "./batchReportShared";

export type { BatchSpeakerOutcome, PipelineStepId } from "./batchReportShared";

export interface BatchReportModalProps {
  open: boolean;
  onClose: () => void;
  outcomes: BatchSpeakerOutcome[];
  stepsRun: PipelineStepId[];
  onRerunFailed?: (speakers: string[]) => void;
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

  const totals = useMemo(() => countTotals(outcomes, stepsRun), [outcomes, stepsRun]);
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

  const columnCount = stepsRun.length + 2;
  const allClean = totals.errored === 0 && totals.skipped === 0 && totals.empty === 0;
  const title = `Batch Report — ${outcomes.length} speakers × ${stepsRun.length} steps`;

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="flex w-[min(90vw,64rem)] flex-col gap-3" data-testid="batch-report-modal">
        <BatchReportSummaryHeader
          totals={totals}
          outcomesCount={outcomes.length}
          allClean={allClean}
        />

        {stepsRun.length === 0 ? (
          <div className="py-10 text-center text-sm text-slate-500">No steps were run.</div>
        ) : (
          <div className="max-h-[60vh] overflow-auto rounded border border-slate-200">
            <table
              className="min-w-full border-collapse text-left text-xs"
              data-testid="batch-report-table"
            >
              <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-600">
                <tr>
                  <th className="border-b border-slate-200 px-3 py-2 font-semibold">Speaker</th>
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
                {outcomes.map((outcome) => (
                  <BatchReportTableRow
                    key={outcome.speaker}
                    outcome={outcome}
                    stepsRun={stepsRun}
                    columnCount={columnCount}
                    isCellOpen={(step) => openCells.has(`${outcome.speaker}:${step}`)}
                    onToggleCell={(step) => toggleCell(outcome.speaker, step)}
                    isBannerOpen={openBanners.has(outcome.speaker)}
                    onToggleBanner={() => toggleBanner(outcome.speaker)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

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
