import { providerLabel } from "./shared";
import { SourcesTable } from "./SourcesTable";
import type { CoverageMatrixProps } from "./types";

function LanguageDetail({ entry, citations }: { entry: NonNullable<CoverageMatrixProps["activeLangEntry"]>; citations: CoverageMatrixProps["report"]["citations"] }) {
  const coveragePct = entry.concepts_total > 0
    ? Math.round((entry.concepts_covered / entry.concepts_total) * 100)
    : 0;
  const providerEntries = Object.entries(entry.per_provider).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  return (
    <div data-testid={`sources-report-lang-${entry.code}`}>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-slate-600">
        <span><strong>{entry.total_forms}</strong> form{entry.total_forms === 1 ? "" : "s"}</span>
        <span><strong>{entry.concepts_covered}</strong> / {entry.concepts_total} concepts ({coveragePct}%)</span>
        {entry.family && <span className="text-slate-400">family: {entry.family}</span>}
      </div>

      {providerEntries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {providerEntries.map(([id, count]) => (
            <span
              key={id}
              className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600"
              title={citations[id]?.citation ?? undefined}
            >
              {providerLabel(id, citations)} <span className="font-mono text-slate-400">· {count}</span>
            </span>
          ))}
        </div>
      )}

      <SourcesTable entry={entry} citations={citations} />
    </div>
  );
}

export function CoverageMatrix({ report, activeLang, setActiveLang, activeLangEntry }: CoverageMatrixProps) {
  return (
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
        {report.languages.map((language) => {
          const isActive = language.code === activeLang;
          return (
            <button
              key={language.code}
              onClick={() => setActiveLang(language.code)}
              data-testid={`sources-report-lang-tab-${language.code}`}
              className={`rounded-full px-3 py-0.5 text-[11px] transition ${
                isActive
                  ? "bg-slate-900 text-white"
                  : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-100"
              }`}
            >
              {language.name} <span className="ml-1 font-mono opacity-70">({language.code})</span>
              <span className="ml-1.5 opacity-70">· {language.total_forms}</span>
            </button>
          );
        })}
      </div>

      {activeLangEntry && <LanguageDetail entry={activeLangEntry} citations={report.citations} />}
    </section>
  );
}
