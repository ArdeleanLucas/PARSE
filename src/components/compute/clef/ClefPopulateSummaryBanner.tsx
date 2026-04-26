import { AlertCircle, CheckCircle2, RefreshCw, X } from "lucide-react";
import type { ClefPopulateSummaryBannerProps } from "./types";

export function ClefPopulateSummaryBanner({ summary, onDismiss, onRetryWithProviders }: ClefPopulateSummaryBannerProps) {
  const isOk = summary.state === "ok";
  return (
    <div
      className={
        "mb-4 flex items-start gap-2 rounded-md border px-3 py-2 text-[11px] "
        + (isOk
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-amber-200 bg-amber-50 text-amber-800")
      }
      data-testid="clef-populate-summary"
    >
      {isOk ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
      <div className="flex-1">
        <div className="font-semibold">
          {isOk
            ? `Populated ${summary.totalFilled} reference form${summary.totalFilled === 1 ? "" : "s"}`
            : "Populate finished with 0 reference forms"}
        </div>
        {Object.keys(summary.perLang).length > 0 && (
          <div className="mt-0.5 font-mono text-[10px] opacity-80">{Object.entries(summary.perLang).map(([code, count]) => `${code}: ${count}`).join(" · ")}</div>
        )}
        {summary.warning && <div className="mt-1">{summary.warning}</div>}
        {!isOk && (
          <div className="mt-2">
            <button
              onClick={onRetryWithProviders}
              className="inline-flex items-center gap-1 rounded border border-amber-300 bg-white px-2 py-0.5 text-[11px] font-semibold text-amber-800 hover:bg-amber-100"
              data-testid="clef-populate-retry"
            >
              <RefreshCw className="h-3 w-3" /> Retry with different providers
            </button>
          </div>
        )}
      </div>
      <button onClick={onDismiss} className="shrink-0 rounded p-0.5 hover:bg-black/5" title="Dismiss" aria-label="Dismiss populate summary">
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
