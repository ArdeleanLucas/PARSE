import { CheckCircle2, CircleSlash, SkipForward, XCircle } from "lucide-react";

export interface BatchReportSummaryTotals {
  ok: number;
  skipped: number;
  empty: number;
  errored: number;
}

export function BatchReportSummaryHeader({
  totals,
  outcomesCount,
  allClean,
}: {
  totals: BatchReportSummaryTotals;
  outcomesCount: number;
  allClean: boolean;
}): JSX.Element {
  return (
    <>
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
        {totals.empty > 0 && (
          <span
            className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800"
            data-testid="batch-report-chip-empty"
            title="Step ran but wrote zero intervals — see per-cell details"
          >
            <CircleSlash className="h-3 w-3" />
            {totals.empty} empty
          </span>
        )}
        <span
          className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-800"
          data-testid="batch-report-chip-errored"
        >
          <XCircle className="h-3 w-3" />
          {totals.errored} errored
        </span>
      </div>

      {allClean && outcomesCount > 0 && (
        <div
          className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
          data-testid="batch-report-all-clean"
        >
          All {outcomesCount} speaker
          {outcomesCount === 1 ? "" : "s"} processed cleanly.
        </div>
      )}
    </>
  );
}
