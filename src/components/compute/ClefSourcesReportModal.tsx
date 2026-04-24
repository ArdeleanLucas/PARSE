import { useCallback, useEffect, useMemo, useState } from "react";
import { X, AlertCircle, Loader2, BookOpen, RefreshCw } from "lucide-react";
import { getClefSourcesReport } from "../../api/client";
import type { ClefSourcesReport, ClefSourcesReportLanguage } from "../../api/types";

/** Human-friendly labels for the provider ids the backend emits. Keep
 *  in sync with ``compare/providers/registry.PROVIDER_PRIORITY`` plus
 *  the ``unknown`` sentinel used for legacy (pre-provenance) entries. */
const PROVIDER_LABELS: Record<string, string> = {
  csv_override: "CSV override",
  lingpy_wordlist: "LingPy wordlist",
  pycldf: "pycldf",
  pylexibank: "pylexibank",
  asjp: "ASJP",
  cldf: "CLDF",
  wikidata: "Wikidata",
  wiktionary: "Wiktionary",
  grokipedia: "Grokipedia",
  literature: "Literature",
  unknown: "Unattributed (legacy)",
};

function providerLabel(id: string): string {
  return PROVIDER_LABELS[id] ?? id;
}

interface ClefSourcesReportModalProps {
  open: boolean;
  onClose: () => void;
}

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
        setActiveLang((prev) =>
          prev && data.languages.some((l) => l.code === prev) ? prev : data.languages[0].code,
        );
      } else {
        setActiveLang(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sources report");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const activeLangEntry: ClefSourcesReportLanguage | null = useMemo(() => {
    if (!report || !activeLang) return null;
    return report.languages.find((l) => l.code === activeLang) ?? null;
  }, [report, activeLang]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={onClose}
      data-testid="clef-sources-report-modal"
    >
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
          <div className="flex items-start gap-2">
            <BookOpen className="mt-0.5 h-4 w-4 text-slate-500" />
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                CLEF Sources Report
              </h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Provenance of every reference form PARSE populated into this corpus.
                Cite the listed providers when a form appears in your thesis.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => void load()}
              disabled={loading}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30"
              aria-label="Refresh report"
              title="Refresh"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={onClose}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center gap-2 px-5 py-6 text-[12px] text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading report…
            </div>
          )}

          {error && !loading && (
            <div className="m-5 flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <div>{error}</div>
            </div>
          )}

          {!loading && !error && report && report.languages.length === 0 && (
            <div className="px-5 py-8 text-center text-[12px] text-slate-500">
              No reference forms populated yet. Run <strong>Borrowing detection
              (CLEF) → Save &amp; populate</strong> to collect forms from the
              configured providers, then come back here.
            </div>
          )}

          {!loading && !error && report && report.languages.length > 0 && (
            <div className="px-5 py-4 space-y-5">
              {/* Providers summary */}
              <section data-testid="sources-report-providers">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Providers used (whole corpus)
                </div>
                {report.providers.length === 0 ? (
                  <div className="text-[12px] text-slate-400">No providers recorded.</div>
                ) : (
                  <ul className="grid grid-cols-2 gap-1.5 text-[12px] sm:grid-cols-3">
                    {report.providers.map((p) => (
                      <li
                        key={p.id}
                        className="flex items-center justify-between rounded border border-slate-100 bg-slate-50 px-2 py-1"
                        data-testid={`sources-report-provider-${p.id}`}
                      >
                        <span className="truncate text-slate-700">{providerLabel(p.id)}</span>
                        <span className="ml-2 shrink-0 font-mono text-[11px] text-slate-500">
                          {p.total_forms} form{p.total_forms === 1 ? "" : "s"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {/* Language tabs */}
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    Per-language breakdown
                  </div>
                  <div className="text-[10px] text-slate-400">
                    Report generated {new Date(report.generated_at).toLocaleString()}
                  </div>
                </div>
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {report.languages.map((l) => {
                    const isActive = l.code === activeLang;
                    return (
                      <button
                        key={l.code}
                        onClick={() => setActiveLang(l.code)}
                        data-testid={`sources-report-lang-tab-${l.code}`}
                        className={`rounded-full px-3 py-0.5 text-[11px] transition ${
                          isActive
                            ? "bg-slate-900 text-white"
                            : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
                        }`}
                      >
                        {l.name}{" "}
                        <span className="ml-1 font-mono opacity-70">({l.code})</span>
                        <span className="ml-1.5 opacity-70">· {l.total_forms}</span>
                      </button>
                    );
                  })}
                </div>

                {activeLangEntry && <LanguageDetail entry={activeLangEntry} />}
              </section>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-100 bg-slate-50 px-5 py-3 text-right">
          <button
            onClick={onClose}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-[12px] font-semibold text-white hover:bg-slate-800"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function LanguageDetail({ entry }: { entry: ClefSourcesReportLanguage }) {
  const coveragePct =
    entry.concepts_total > 0
      ? Math.round((entry.concepts_covered / entry.concepts_total) * 100)
      : 0;

  // Sort providers by contribution desc, then alpha, so the same
  // ordering shows up in the per-language summary as in the whole-corpus
  // header — makes flicking between tabs less disorienting.
  const providerEntries = Object.entries(entry.per_provider).sort((a, b) =>
    b[1] - a[1] || a[0].localeCompare(b[0]),
  );

  return (
    <div data-testid={`sources-report-lang-${entry.code}`}>
      {/* Summary line */}
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-slate-600">
        <span>
          <strong>{entry.total_forms}</strong> form{entry.total_forms === 1 ? "" : "s"}
        </span>
        <span>
          <strong>{entry.concepts_covered}</strong> / {entry.concepts_total} concepts (
          {coveragePct}%)
        </span>
        {entry.family && (
          <span className="text-slate-400">family: {entry.family}</span>
        )}
      </div>

      {/* Per-provider totals for this language */}
      {providerEntries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {providerEntries.map(([id, n]) => (
            <span
              key={id}
              className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600"
            >
              {providerLabel(id)} <span className="font-mono text-slate-400">· {n}</span>
            </span>
          ))}
        </div>
      )}

      {/* Per-form table */}
      {entry.forms.length === 0 ? (
        <div className="rounded border border-slate-100 bg-slate-50 px-3 py-2 text-[12px] text-slate-500">
          No forms recorded for this language yet.
        </div>
      ) : (
        <div className="max-h-80 overflow-y-auto rounded border border-slate-100">
          <table className="w-full border-collapse text-left text-[12px]">
            <thead className="sticky top-0 bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-1.5 font-semibold">Concept</th>
                <th className="px-3 py-1.5 font-semibold">Form</th>
                <th className="px-3 py-1.5 font-semibold">Sources</th>
              </tr>
            </thead>
            <tbody>
              {entry.forms.map((f, idx) => (
                <tr
                  key={`${f.concept_en}-${idx}`}
                  className="border-t border-slate-100"
                  data-testid={`sources-report-form-row-${entry.code}-${idx}`}
                >
                  <td className="px-3 py-1.5 font-mono text-slate-600">{f.concept_en}</td>
                  <td className="px-3 py-1.5 font-mono text-slate-900">{f.form}</td>
                  <td className="px-3 py-1.5">
                    <div className="flex flex-wrap gap-1">
                      {f.sources.map((s) => (
                        <span
                          key={s}
                          className={`rounded px-1.5 py-0.5 text-[10px] ${
                            s === "unknown"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-slate-100 text-slate-700"
                          }`}
                        >
                          {providerLabel(s)}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
