import { providerLabel } from "./shared";
import type { SourcesTableProps } from "./types";

export function SourcesTable({ entry, citations }: SourcesTableProps) {
  if (entry.forms.length === 0) {
    return (
      <div className="rounded border border-slate-100 bg-slate-50 px-3 py-2 text-[12px] text-slate-500">
        No forms recorded for this language yet.
      </div>
    );
  }

  return (
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
          {entry.forms.map((form, idx) => (
            <tr
              key={`${form.concept_en}-${idx}`}
              className="border-t border-slate-100"
              data-testid={`sources-report-form-row-${entry.code}-${idx}`}
            >
              <td className="px-3 py-1.5 font-mono text-slate-600">{form.concept_en}</td>
              <td className="px-3 py-1.5 font-mono text-slate-900">{form.form}</td>
              <td className="px-3 py-1.5">
                <div className="flex flex-wrap gap-1">
                  {form.sources.map((source) => (
                    <span
                      key={source}
                      className={`rounded px-1.5 py-0.5 text-[10px] ${
                        source === "unknown"
                          ? "bg-amber-50 text-amber-700"
                          : citations[source]?.type === "ai"
                            ? "bg-rose-50 text-rose-700"
                            : "bg-slate-100 text-slate-700"
                      }`}
                      title={citations[source]?.citation ?? undefined}
                    >
                      {providerLabel(source, citations)}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
