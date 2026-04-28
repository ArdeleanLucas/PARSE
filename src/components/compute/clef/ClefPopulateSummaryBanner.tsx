import { useEffect, useMemo, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Copy, RefreshCw, X } from "lucide-react";
import type { ClefPopulateSummaryBannerProps } from "./types";

export function ClefPopulateSummaryBanner({ summary, onDismiss, onRetryWithProviders }: ClefPopulateSummaryBannerProps) {
  const isOk = summary.state === "ok";
  const warnings = useMemo(
    () => (summary.warnings ?? []).filter((warning): warning is string => typeof warning === "string" && warning.trim().length > 0),
    [summary.warnings],
  );

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
        <PopulateWarnings warnings={warnings} />
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

function PopulateWarnings({ warnings }: { warnings: string[] }) {
  const [expanded, setExpanded] = useState(warnings.length <= 3);
  const warningsListId = "clef-populate-warnings-list";

  useEffect(() => {
    setExpanded(warnings.length <= 3);
  }, [warnings]);

  if (warnings.length === 0) {
    return null;
  }

  const copyWarnings = async () => {
    try {
      await navigator.clipboard.writeText(warnings.join("\n"));
    } catch {
      // Clipboard access is best-effort only.
    }
  };

  return (
    <section className="mt-3 rounded-lg border border-amber-200 bg-amber-50/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-600"
          aria-expanded={expanded}
          aria-controls={warningsListId}
        >
          {expanded ? <ChevronDown className="h-3 w-3 text-amber-700" /> : <ChevronRight className="h-3 w-3 text-amber-700" />}
          {warnings.length} provider warning{warnings.length === 1 ? "" : "s"}
        </button>
        <button
          type="button"
          onClick={() => void copyWarnings()}
          className="inline-flex items-center gap-1 rounded border border-amber-200 bg-white px-2 py-0.5 text-[11px] font-medium text-amber-800 hover:bg-amber-50"
          title="Copy warnings to clipboard"
          aria-label="Copy warnings"
        >
          <Copy className="h-3 w-3" /> Copy warnings
        </button>
      </div>
      <div className="mt-2 text-[11px] text-slate-500">Provider readiness warnings from the populate response.</div>
      {expanded && (
        <ul id={warningsListId} className="mt-2 space-y-1.5">
          {warnings.map((warning, index) => (
            <li
              key={`${warning}-${index}`}
              className="flex items-start gap-2 rounded-md bg-amber-50 px-2 py-1.5 text-[12px] text-slate-600 ring-1 ring-amber-200"
              data-testid="clef-populate-warning"
            >
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-700" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
