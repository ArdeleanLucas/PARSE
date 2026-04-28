import { AlertCircle, ArrowLeft, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { orderedUsedProviders, providerLabel } from "./shared";
import type { ConceptProviderMatrixProps } from "./types";

interface ConceptProviderEntry {
  language: string;
  concept_en: string;
  form: string;
  source: string;
}

interface MatrixRow {
  concept: string;
  counts: Record<string, number>;
  entries: Record<string, ConceptProviderEntry[]>;
}

export function MatrixCell({ count, errored, onClick, dataTestId }: { count: number; errored: boolean; onClick: () => void; dataTestId?: string }) {
  if (errored) {
    return (
      <button data-testid={dataTestId} onClick={onClick} className="flex h-7 w-full items-center justify-center rounded bg-rose-50 text-[11px] font-semibold text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100" title="Errored — click for details">
        ✕
      </button>
    );
  }
  if (count === 0) {
    return <div data-testid={dataTestId} className="h-7 w-full rounded bg-slate-50 ring-1 ring-slate-100" aria-label="No forms" />;
  }
  return (
    <button data-testid={dataTestId} onClick={onClick} className="flex h-7 w-full items-center justify-center rounded bg-emerald-50 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-100" title={`${count} form${count === 1 ? "" : "s"} — click to drill down`}>
      ●{count}
    </button>
  );
}

export function ConceptProviderMatrix({ report }: ConceptProviderMatrixProps) {
  const providers = useMemo(() => orderedUsedProviders(report), [report]);
  const rows = useMemo<MatrixRow[]>(() => {
    const byConcept = new Map<string, MatrixRow>();
    for (const language of report.languages) {
      for (const form of language.forms) {
        const row = byConcept.get(form.concept_en) ?? { concept: form.concept_en, counts: {}, entries: {} };
        for (const source of form.sources) {
          row.counts[source] = (row.counts[source] ?? 0) + 1;
          row.entries[source] = [...(row.entries[source] ?? []), {
            language: language.code,
            concept_en: form.concept_en,
            form: form.form,
            source,
          }];
        }
        byConcept.set(form.concept_en, row);
      }
    }
    return Array.from(byConcept.values()).sort((a, b) => a.concept.localeCompare(b.concept));
  }, [report.languages]);
  const [page, setPage] = useState(0);
  const [drawer, setDrawer] = useState<{ concept: string; providerId: string; entries: ConceptProviderEntry[] } | null>(null);

  const pageSize = 50;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const pagedRows = rows.slice(page * pageSize, page * pageSize + pageSize);

  return (
    <section className="space-y-3" data-testid="concept-provider-matrix">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">Concept × provider matrix</h3>
          <p className="mt-1 text-[12px] text-slate-600">
            Green cells show how many forms a provider contributed for each concept. Click a cell to inspect the actual forms.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {pageCount > 1 && (
            <span className="text-[11px] text-slate-400">Page {page + 1} of {pageCount}</span>
          )}
          <button
            type="button"
            disabled
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-400 disabled:cursor-not-allowed"
            title="Follow-up: the report payload does not yet expose failed-provider metadata to target retries from this modal."
          >
            <RefreshCw className="h-3 w-3" /> Re-run failed providers
          </button>
        </div>
      </div>

      <div className="overflow-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full border-collapse text-left text-[12px]">
          <thead className="sticky top-0 z-20 bg-slate-50 text-[11px] uppercase tracking-wider text-slate-600">
            <tr>
              <th className="sticky left-0 z-30 min-w-[180px] border-b border-slate-200 bg-slate-50 px-3 py-2 font-semibold">Concept</th>
              {providers.map((provider) => (
                <th key={provider.id} className="min-w-[120px] border-b border-slate-200 px-3 py-2 text-center font-semibold">
                  {providerLabel(provider.id, report.citations)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map((row) => (
              <tr key={row.concept} className="border-t border-slate-100">
                <td className="sticky left-0 z-10 border-r border-slate-100 bg-white px-3 py-2 font-mono text-slate-700">{row.concept}</td>
                {providers.map((provider) => {
                  const entries = row.entries[provider.id] ?? [];
                  return (
                    <td key={`${row.concept}-${provider.id}`} className="px-2 py-2">
                      <MatrixCell
                        dataTestId={`concept-provider-cell-${row.concept}-${provider.id}`}
                        count={row.counts[provider.id] ?? 0}
                        errored={false}
                        onClick={() => setDrawer({ concept: row.concept, providerId: provider.id, entries })}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-end gap-2 text-[11px]">
          <button type="button" onClick={() => setPage((current) => Math.max(0, current - 1))} disabled={page === 0} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Previous</button>
          <button type="button" onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))} disabled={page >= pageCount - 1} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Next</button>
        </div>
      )}

      {drawer && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-[0_1px_0_rgba(15,23,42,0.03)]" data-testid="concept-provider-drawer">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-600">Provider drill-down</div>
              <h4 className="mt-1 text-[13px] font-semibold text-slate-900">{drawer.concept} · {providerLabel(drawer.providerId, report.citations)}</h4>
              <div className="mt-1 text-[12px] text-slate-600">{drawer.entries.length} form{drawer.entries.length === 1 ? "" : "s"} returned for this concept/provider pair.</div>
            </div>
            <button type="button" onClick={() => setDrawer(null)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">
              <ArrowLeft className="h-3 w-3" /> Back
            </button>
          </div>
          {drawer.entries.length === 0 ? (
            <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[11px] text-amber-800">
              <AlertCircle className="h-3.5 w-3.5" />
              No form payload is attached to this cell yet.
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-[11px] text-slate-500">{report.citations[drawer.providerId]?.citation ?? "No citation metadata available."}</div>
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full border-collapse text-left text-[12px]">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-3 py-2 font-semibold">Language</th>
                      <th className="px-3 py-2 font-semibold">Form</th>
                      <th className="px-3 py-2 font-semibold">Citation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drawer.entries.map((entry, index) => (
                      <tr key={`${entry.language}-${entry.form}-${index}`} className="border-t border-slate-100">
                        <td className="px-3 py-2 font-mono text-slate-600">{entry.language}</td>
                        <td className="px-3 py-2 font-mono text-slate-900">{entry.form}</td>
                        <td className="px-3 py-2 text-slate-600">{report.citations[drawer.providerId]?.citation ?? providerLabel(drawer.providerId, report.citations)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
