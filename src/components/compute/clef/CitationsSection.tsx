import { Copy, Download, ExternalLink } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import type { ClefSourcesReport } from "../../../api/types";
import { buildBibtex, copyText, downloadBibtex, orderedUsedProviders } from "./shared";

export function CitationsSection({ report }: { report: ClefSourcesReport }) {
  const used = useMemo(() => orderedUsedProviders(report), [report]);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const flashCopied = useCallback((key: string) => {
    setCopiedKey(key);
    setTimeout(() => {
      setCopiedKey((prev) => (prev === key ? null : prev));
    }, 1500);
  }, []);

  const onCopyCitation = useCallback(async (id: string, citation: string) => {
    const ok = await copyText(citation);
    if (ok) flashCopied(`cite:${id}`);
  }, [flashCopied]);

  const onCopyBibtex = useCallback(async (id: string, bibtex: string) => {
    if (!bibtex) return;
    const ok = await copyText(bibtex);
    if (ok) flashCopied(`bib:${id}`);
  }, [flashCopied]);

  const onExportBibtex = useCallback(() => {
    downloadBibtex(buildBibtex(used, report.citations));
  }, [report.citations, used]);

  const exportable = used.some((provider) => report.citations[provider.id]?.bibtex);
  if (used.length === 0) return null;

  return (
    <section data-testid="sources-report-citations">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Academic citations
        </div>
        {exportable && (
          <button
            onClick={onExportBibtex}
            data-testid="sources-report-export-bibtex"
            className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50"
            title="Download a .bib file with every provider's BibTeX entry"
          >
            <Download className="h-3 w-3" /> Export BibTeX
          </button>
        )}
      </div>
      <ul className="space-y-2">
        {used.map(({ id }) => {
          const citation = report.citations[id];
          if (!citation) return null;
          const isAi = citation.type === "ai";
          const isSentinel = citation.type === "sentinel";
          const isManual = citation.type === "manual";
          const accent = isAi
            ? "border-rose-200 bg-rose-50"
            : isSentinel
              ? "border-amber-200 bg-amber-50"
              : isManual
                ? "border-slate-200 bg-slate-50"
                : "border-slate-200 bg-white";
          return (
            <li
              key={id}
              data-testid={`sources-report-citation-${id}`}
              className={`rounded-md border ${accent} px-3 py-2 text-[12px]`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-semibold text-slate-800">{citation.label}</div>
                <div className="flex shrink-0 items-center gap-1 text-[10px] text-slate-500">
                  {citation.license && (
                    <span className="rounded bg-white/70 px-1.5 py-0.5 font-mono">{citation.license}</span>
                  )}
                  {citation.url && (
                    <a
                      href={citation.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-0.5 text-slate-500 hover:text-slate-800"
                      title={citation.url}
                    >
                      <ExternalLink className="h-3 w-3" /> URL
                    </a>
                  )}
                  {citation.doi && (
                    <a
                      href={`https://doi.org/${citation.doi}`}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-0.5 text-slate-500 hover:text-slate-800"
                      title={`DOI: ${citation.doi}`}
                    >
                      <ExternalLink className="h-3 w-3" /> DOI
                    </a>
                  )}
                </div>
              </div>
              <p className="mt-1 text-slate-700">{citation.citation}</p>
              {citation.note && (
                <p className={`mt-1 text-[11px] ${isAi ? "text-rose-700" : isSentinel ? "text-amber-700" : "text-slate-500"}`}>
                  {citation.note}
                </p>
              )}
              <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
                <button
                  onClick={() => void onCopyCitation(id, citation.citation)}
                  data-testid={`sources-report-copy-cite-${id}`}
                  className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-slate-600 hover:bg-slate-50"
                >
                  <Copy className="h-3 w-3" />
                  {copiedKey === `cite:${id}` ? "Copied!" : "Copy citation"}
                </button>
                {citation.bibtex && (
                  <button
                    onClick={() => void onCopyBibtex(id, citation.bibtex)}
                    data-testid={`sources-report-copy-bibtex-${id}`}
                    className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-slate-600 hover:bg-slate-50"
                  >
                    <Copy className="h-3 w-3" />
                    {copiedKey === `bib:${id}` ? "Copied!" : "Copy BibTeX"}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
