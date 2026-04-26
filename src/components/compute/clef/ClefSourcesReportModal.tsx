import { AlertCircle, BookOpen, Loader2, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getClefSourcesReport } from "../../../api/client";
import type { ClefSourcesReport, ClefSourcesReportLanguage } from "../../../api/types";
import { CitationsSection } from "./CitationsSection";
import { CoverageMatrix } from "./CoverageMatrix";
import type { ClefSourcesReportModalProps } from "./types";

export function ClefSourcesReportModal({ open, onClose }: ClefSourcesReportModalProps) {
  const [report, setReport] = useState<ClefSourcesReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeLang, setActiveLang] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getClefSourcesReport();
      setReport(data);
      if (data.languages.length > 0) {
        setActiveLang((prev) => prev && data.languages.some((language) => language.code === prev) ? prev : data.languages[0].code);
      } else {
        setActiveLang(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sources report");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [load, open]);

  const activeLangEntry: ClefSourcesReportLanguage | null = useMemo(() => {
    if (!report || !activeLang) return null;
    return report.languages.find((language) => language.code === activeLang) ?? null;
  }, [activeLang, report]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={onClose} data-testid="clef-sources-report-modal">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
          <div className="flex items-start gap-2">
            <BookOpen className="mt-0.5 h-4 w-4 text-slate-500" />
            <div>
              <h2 className="text-sm font-semibold text-slate-900">CLEF Sources Report</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Provenance of every reference form PARSE populated into this corpus. Cite the listed providers when a form appears in your thesis.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button onClick={() => void load()} disabled={loading} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30" aria-label="Refresh report" title="Refresh">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && <div className="flex items-center gap-2 px-5 py-6 text-[12px] text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading report…</div>}
          {error && !loading && <div className="m-5 flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800"><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><div>{error}</div></div>}
          {!loading && !error && report && report.languages.length === 0 && (
            <div className="px-5 py-8 text-center text-[12px] text-slate-500">
              No reference forms populated yet. Run <strong>Borrowing detection (CLEF) → Save &amp; populate</strong> to collect forms from the configured providers, then come back here.
            </div>
          )}
          {!loading && !error && report && report.languages.length > 0 && (
            <div className="space-y-5 px-5 py-4">
              <section data-testid="sources-report-providers">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Providers used (whole corpus)</div>
                {report.providers.length === 0 ? (
                  <div className="text-[12px] text-slate-400">No providers recorded.</div>
                ) : (
                  <ul className="grid grid-cols-2 gap-1.5 text-[12px] sm:grid-cols-3">
                    {report.providers.map((provider) => (
                      <li key={provider.id} className="flex items-center justify-between rounded border border-slate-100 bg-slate-50 px-2 py-1" data-testid={`sources-report-provider-${provider.id}`}>
                        <span className="truncate text-slate-700">{report.citations[provider.id]?.label ?? provider.id}</span>
                        <span className="ml-2 shrink-0 font-mono text-[11px] text-slate-500">{provider.total_forms} form{provider.total_forms === 1 ? "" : "s"}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <CitationsSection report={report} />
              <CoverageMatrix report={report} activeLang={activeLang} setActiveLang={setActiveLang} activeLangEntry={activeLangEntry} />
            </div>
          )}
        </div>

        <div className="border-t border-slate-100 bg-slate-50 px-5 py-3 text-right">
          <button onClick={onClose} className="rounded-md bg-slate-900 px-4 py-1.5 text-[12px] font-semibold text-white hover:bg-slate-800">Close</button>
        </div>
      </div>
    </div>
  );
}
