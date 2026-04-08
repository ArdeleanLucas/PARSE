// useExport — all Compare Mode export formats.
// LingPy TSV: P0 — server-side via /api/export/lingpy.
// NEXUS: server-side (501 until backend impl).
// CSV: client-side only from enrichmentStore.
import { getLingPyExport, getNEXUSExport } from "../api/client";
import { useEnrichmentStore } from "../stores/enrichmentStore";

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const CSV_HEADERS = ["ID", "DOCULECT", "CONCEPT", "IPA", "COGID", "TOKENS", "NOTE"] as const;

export function useExport() {
  const data = useEnrichmentStore((s) => s.data);

  const exportLingPyTSV = async (): Promise<void> => {
    const blob = await getLingPyExport();
    triggerDownload(blob, "parse-wordlist.tsv");
  };

  const exportNEXUS = async (): Promise<void> => {
    const blob = await getNEXUSExport();
    triggerDownload(blob, "parse-wordlist.nex");
  };

  const exportCSV = (): void => {
    const rows: string[][] = [[...CSV_HEADERS]];
    let id = 1;
    for (const [conceptId, entry] of Object.entries(data)) {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
      const e = entry as Record<string, unknown>;
      const ipaMap = (e.ipa_computed ?? {}) as Record<string, string>;
      for (const [doculect, ipa] of Object.entries(ipaMap)) {
        rows.push([String(id++), doculect, conceptId, ipa, "0", ipa, ""]);
      }
    }
    const tsv = rows.map((r) => r.join("\t")).join("\n");
    const blob = new Blob([tsv], { type: "text/tab-separated-values;charset=utf-8" });
    triggerDownload(blob, "parse-export.csv");
  };

  return { exportLingPyTSV, exportNEXUS, exportCSV };
}
