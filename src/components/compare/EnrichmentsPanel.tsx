import { useEffect, useState } from "react";
import { Spinner } from "../shared/Spinner";
import { Badge } from "../shared/Badge";
import { Button } from "../shared/Button";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { useTagStore } from "../../stores/tagStore";

interface EnrichmentsPanelProps {
  activeConcept: string | null;
}

interface CognateSets {
  [groupLetter: string]: string[];
}

interface EnrichmentEntry {
  cognate_sets?: CognateSets;
  manual_overrides?: {
    cognate_sets?: Record<string, CognateSets>;
    borrowing_flags?: Record<string, string>;
    [key: string]: unknown;
  };
  phoneme_distances?: Record<string, Record<string, number>>;
  ipa_computed?: Record<string, string>;
  similarity?: Record<string, unknown>;
  [key: string]: unknown;
}

function isRecord(val: unknown): val is Record<string, unknown> {
  return val !== null && typeof val === "object" && !Array.isArray(val);
}

function getEntry(data: Record<string, unknown>, key: string): EnrichmentEntry | null {
  const raw = data[key];
  if (!isRecord(raw)) return null;
  return raw as EnrichmentEntry;
}

function getCognates(entry: EnrichmentEntry, conceptId: string): CognateSets | null {
  // Prefer manual_overrides.cognate_sets[conceptId] first, fall back to entry.cognate_sets
  const manual = entry.manual_overrides;
  if (manual && isRecord(manual.cognate_sets)) {
    const manualForConcept = (manual.cognate_sets as Record<string, unknown>)[conceptId];
    if (isRecord(manualForConcept)) {
      return manualForConcept as CognateSets;
    }
  }
  if (isRecord(entry.cognate_sets)) {
    return entry.cognate_sets as CognateSets;
  }
  return null;
}

export function EnrichmentsPanel({ activeConcept }: EnrichmentsPanelProps) {
  const data = useEnrichmentStore((s) => s.data);
  const loading = useEnrichmentStore((s) => s.loading);
  const load = useEnrichmentStore((s) => s.load);
  const save = useEnrichmentStore((s) => s.save);
  const getTagsForConcept = useTagStore((s) => s.getTagsForConcept);

  const [exportLoading, setExportLoading] = useState(false);

  useEffect(() => {
    if (activeConcept && Object.keys(data).length === 0) {
      load().catch(() => {});
    }
  }, [activeConcept, data, load]);

  if (!activeConcept) {
    return (
      <div data-testid="enrichments-placeholder" style={{ padding: "1rem", fontFamily: "monospace", color: "#9ca3af" }}>
        Select a concept
      </div>
    );
  }

  if (loading) {
    return (
      <div data-testid="enrichments-loading" style={{ padding: "1rem" }}>
        <Spinner label="Loading enrichments..." />
      </div>
    );
  }

  const entry = getEntry(data, activeConcept);
  const tags = getTagsForConcept(activeConcept);

  if (!entry) {
    return (
      <div data-testid="enrichments-nodata" style={{ padding: "1rem", fontFamily: "monospace", color: "#9ca3af" }}>
        No data
      </div>
    );
  }

  const cognates = getCognates(entry, activeConcept);
  const ipaComputed = isRecord(entry.ipa_computed) ? (entry.ipa_computed as Record<string, string>) : null;
  const phonemeDist = isRecord(entry.phoneme_distances) ? (entry.phoneme_distances as Record<string, Record<string, number>>) : null;

  // Truncate phoneme distance table to 4 speakers max
  const pdSpeakers = phonemeDist ? Object.keys(phonemeDist).slice(0, 4) : [];

  function handleVerifyCognates() {
    const existing = entry?.manual_overrides ?? {};
    const currentCognates = cognates ?? {};
    save({
      manual_overrides: {
        ...existing,
        cognate_sets: { [activeConcept!]: currentCognates },
      },
    });
  }

  function handleFlagBorrowing() {
    const existing = entry?.manual_overrides ?? {};
    const existingFlags = isRecord(existing.borrowing_flags) ? existing.borrowing_flags : {};
    save({
      manual_overrides: {
        ...existing,
        borrowing_flags: { ...existingFlags, [activeConcept!]: "flagged" },
      },
    });
  }

  async function handleExportLingPy() {
    setExportLoading(true);
    try {
      const response = await fetch("/api/export/lingpy");
      if (!response.ok) throw new Error("Export failed");
      const text = await response.text();
      const blob = new Blob([text], { type: "text/tab-separated-values" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "lingpy-export.tsv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // export error handled silently
    } finally {
      setExportLoading(false);
    }
  }

  return (
    <div data-testid="enrichments-panel" style={{ padding: "1rem", fontFamily: "monospace" }}>
      {/* Header */}
      <div style={{ marginBottom: "0.75rem" }}>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.375rem" }}>
          Enrichments — #{activeConcept}
        </div>
        {tags.length > 0 && (
          <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
            {tags.map((t) => (
              <Badge key={t.id} label={t.label} color={t.color} />
            ))}
          </div>
        )}
      </div>

      {/* Cognate sets */}
      {cognates && Object.keys(cognates).length > 0 && (
        <div data-testid="cognate-sets" style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem" }}>Cognate Sets</div>
          {Object.entries(cognates).map(([group, speakers]) => (
            <div key={group} style={{ marginBottom: "0.25rem" }}>
              <span style={{ fontWeight: 500 }}>{group}:</span>{" "}
              {Array.isArray(speakers) ? speakers.join(", ") : String(speakers)}
            </div>
          ))}
        </div>
      )}

      {/* IPA computed */}
      {ipaComputed && Object.keys(ipaComputed).length > 0 && (
        <div data-testid="ipa-computed" style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem" }}>IPA Computed</div>
          {Object.entries(ipaComputed).map(([speaker, ipa]) => (
            <div key={speaker}>
              <span style={{ fontWeight: 500 }}>{speaker}:</span> {ipa}
            </div>
          ))}
        </div>
      )}

      {/* Phoneme distances */}
      {pdSpeakers.length > 0 && phonemeDist && (
        <div data-testid="phoneme-distances" style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem" }}>Phoneme Distances</div>
          <table style={{ borderCollapse: "collapse", fontSize: "0.75rem" }}>
            <thead>
              <tr>
                <th style={{ padding: "0.25rem", border: "1px solid #d1d5db" }}></th>
                {pdSpeakers.map((s) => (
                  <th key={s} style={{ padding: "0.25rem", border: "1px solid #d1d5db" }}>{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pdSpeakers.map((row) => (
                <tr key={row}>
                  <td style={{ padding: "0.25rem", border: "1px solid #d1d5db", fontWeight: 500 }}>{row}</td>
                  {pdSpeakers.map((col) => {
                    const rowData = phonemeDist[row];
                    const val = isRecord(rowData) ? (rowData as Record<string, number>)[col] : undefined;
                    return (
                      <td key={col} style={{ padding: "0.25rem", border: "1px solid #d1d5db", textAlign: "right" }}>
                        {val !== undefined ? val.toFixed(2) : "-"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
        <Button size="sm" variant="primary" onClick={handleVerifyCognates}>
          Verify Cognates
        </Button>
        <Button size="sm" variant="secondary" onClick={handleFlagBorrowing}>
          Flag Borrowing
        </Button>
        <Button size="sm" variant="secondary" loading={exportLoading} onClick={handleExportLingPy}>
          Export LingPy TSV
        </Button>
      </div>
    </div>
  );
}
