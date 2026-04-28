import type { ClefProviderEntry, ClefSourceCitation, ClefSourcesReport } from "../../../api/types";

export const FALLBACK_PROVIDER_LABELS: Record<string, string> = {
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

export const PROVIDER_GROUPS = [
  {
    id: "open-lexical-databases",
    label: "Open lexical databases",
    providerIds: ["wiktionary", "wikidata", "asjp", "cldf", "pycldf", "pylexibank", "lingpy_wordlist"],
  },
  {
    id: "local-sources",
    label: "Local sources",
    providerIds: ["csv_override", "literature"],
  },
  {
    id: "llm-augmented-search",
    label: "LLM-augmented search",
    providerIds: ["grokipedia"],
  },
] as const;

export const PROVIDER_SUBTITLES: Record<string, string> = {
  wiktionary: "Public dictionary API",
  wikidata: "Structured lexical graph",
  asjp: "Comparative wordlist dataset",
  cldf: "Cross-linguistic dataset bundle",
  pycldf: "Python CLDF tooling",
  pylexibank: "Lexibank corpus wrappers",
  lingpy_wordlist: "LingPy project wordlists",
  csv_override: "Workspace CSV overrides",
  literature: "Workspace literature notes",
  grokipedia: "xAI/OpenAI assisted lookup",
};

export const ALL_PROVIDER_IDS = PROVIDER_GROUPS.flatMap((group) => [...group.providerIds]);

export function normalizeClefProviders(entries: ClefProviderEntry[]): ClefProviderEntry[] {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  return ALL_PROVIDER_IDS.map((id) => byId.get(id) ?? { id, name: FALLBACK_PROVIDER_LABELS[id] ?? id });
}

export function providerLabel(id: string, citations?: Record<string, ClefSourceCitation>): string {
  return citations?.[id]?.label ?? FALLBACK_PROVIDER_LABELS[id] ?? id;
}

export async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // fall through to legacy path
    }
  }
  if (typeof document !== "undefined") {
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(textarea);
      return ok;
    } catch {
      return false;
    }
  }
  return false;
}

export function buildBibtex(
  providersUsed: ReadonlyArray<{ id: string }>,
  citations: Record<string, ClefSourceCitation>,
): string {
  const blocks: string[] = [];
  for (const { id } of providersUsed) {
    const citation = citations[id];
    if (citation && citation.bibtex && citation.bibtex.trim()) {
      blocks.push(citation.bibtex.trim());
    }
  }
  return blocks.join("\n\n") + (blocks.length > 0 ? "\n" : "");
}

export function downloadBibtex(text: string, filename = "clef-sources.bib"): void {
  if (typeof document === "undefined") return;
  const blob = new Blob([text], { type: "application/x-bibtex;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function orderedUsedProviders(report: ClefSourcesReport): Array<{ id: string; total_forms: number }> {
  const used = new Map(report.providers.map((provider) => [provider.id, provider]));
  const out: Array<{ id: string; total_forms: number }> = [];
  for (const id of report.citation_order ?? []) {
    const entry = used.get(id);
    if (entry) {
      out.push(entry);
      used.delete(id);
    }
  }
  for (const entry of report.providers) {
    if (used.has(entry.id)) {
      out.push(entry);
      used.delete(entry.id);
    }
  }
  return out;
}
