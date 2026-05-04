import { useEffect, useMemo, useState } from "react";
import { Spinner } from "../shared/Spinner";
import { Badge } from "../shared/Badge";
import { Button } from "../shared/Button";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useConfigStore } from "../../stores/configStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { useTagStore } from "../../stores/tagStore";
import { useUIStore } from "../../stores/uiStore";
import { useExport } from "../../hooks/useExport";
import { useComputeJob } from "../../hooks/useComputeJob";

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function getEntry(data: Record<string, unknown>, key: string): EnrichmentEntry | null {
  const raw = data[key];
  if (!isRecord(raw)) {
    return null;
  }
  return raw as EnrichmentEntry;
}

function getCognates(entry: EnrichmentEntry, conceptId: string): CognateSets | null {
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
  const data = useEnrichmentStore((store) => store.data);
  const loading = useEnrichmentStore((store) => store.loading);
  const load = useEnrichmentStore((store) => store.load);
  const save = useEnrichmentStore((store) => store.save);
  const records = useAnnotationStore((store) => store.records);
  const tagVocabulary = useTagStore((store) => store.tags);
  const selectedSpeakers = useUIStore((store) => store.selectedSpeakers) ?? [];
  const configSpeakers = useConfigStore((store) => store.config?.speakers ?? []);

  const { exportLingPyTSV } = useExport();
  const { start: startCompute, state: computeState } = useComputeJob("cognates");

  const [exportLoading, setExportLoading] = useState(false);
  const targetSpeakers = useMemo(() => {
    if (selectedSpeakers.length > 0) return selectedSpeakers;
    return configSpeakers.length > 0 ? configSpeakers : Object.keys(records);
  }, [configSpeakers, records, selectedSpeakers]);
  const conceptTags = useMemo(() => {
    if (!activeConcept) return [];
    const tagIds = new Set<string>();
    for (const speaker of targetSpeakers) {
      for (const tagId of records[speaker]?.concept_tags?.[activeConcept] ?? []) {
        tagIds.add(tagId);
      }
    }
    return tagVocabulary.filter((tag) => tagIds.has(tag.id));
  }, [activeConcept, records, tagVocabulary, targetSpeakers]);

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

  const conceptId = activeConcept;
  const entry = getEntry(data, conceptId);
  const tags = conceptTags;

  if (!entry) {
    return (
      <div data-testid="enrichments-nodata" style={{ padding: "1rem", fontFamily: "monospace", color: "#9ca3af" }}>
        No data
      </div>
    );
  }

  const entryData = entry;
  const cognates = getCognates(entryData, conceptId);
  const ipaComputed = isRecord(entryData.ipa_computed)
    ? (entryData.ipa_computed as Record<string, string>)
    : null;
  const phonemeDist = isRecord(entryData.phoneme_distances)
    ? (entryData.phoneme_distances as Record<string, Record<string, number>>)
    : null;
  const pdSpeakers = phonemeDist ? Object.keys(phonemeDist).slice(0, 4) : [];

  function handleVerifyCognates() {
    const existing = entryData.manual_overrides ?? {};
    const currentCognates = cognates ?? {};
    void save({
      manual_overrides: {
        ...existing,
        cognate_sets: { [conceptId]: currentCognates },
      },
    });
  }

  function handleFlagBorrowing() {
    const existing = entryData.manual_overrides ?? {};
    const existingFlags = isRecord(existing.borrowing_flags) ? existing.borrowing_flags : {};
    void save({
      manual_overrides: {
        ...existing,
        borrowing_flags: { ...existingFlags, [conceptId]: "flagged" },
      },
    });
  }

  async function handleExportLingPy() {
    setExportLoading(true);
    try {
      await exportLingPyTSV();
    } catch {
      // handled by API-level errors and user retry
    } finally {
      setExportLoading(false);
    }
  }

  async function handleRunCompute() {
    await startCompute();
  }

  return (
    <div data-testid="enrichments-panel" style={{ padding: "1rem", fontFamily: "monospace" }}>
      <div style={{ marginBottom: "0.75rem" }}>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.375rem" }}>
          Enrichments — #{activeConcept}
        </div>
        {tags.length > 0 && (
          <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
            {tags.map((tag) => (
              <Badge key={tag.id} label={tag.label} color={tag.color} />
            ))}
          </div>
        )}
      </div>

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

      {pdSpeakers.length > 0 && phonemeDist && (
        <div data-testid="phoneme-distances" style={{ marginBottom: "0.75rem" }}>
          <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem" }}>Phoneme Distances</div>
          <table style={{ borderCollapse: "collapse", fontSize: "0.75rem" }}>
            <thead>
              <tr>
                <th style={{ padding: "0.25rem", border: "1px solid #d1d5db" }}></th>
                {pdSpeakers.map((speaker) => (
                  <th key={speaker} style={{ padding: "0.25rem", border: "1px solid #d1d5db" }}>
                    {speaker}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pdSpeakers.map((rowSpeaker) => (
                <tr key={rowSpeaker}>
                  <td style={{ padding: "0.25rem", border: "1px solid #d1d5db", fontWeight: 500 }}>
                    {rowSpeaker}
                  </td>
                  {pdSpeakers.map((colSpeaker) => {
                    const rowData = phonemeDist[rowSpeaker];
                    const value = isRecord(rowData)
                      ? (rowData as Record<string, number>)[colSpeaker]
                      : undefined;
                    return (
                      <td key={colSpeaker} style={{ padding: "0.25rem", border: "1px solid #d1d5db", textAlign: "right" }}>
                        {value !== undefined ? value.toFixed(2) : "-"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
        <Button size="sm" variant="primary" onClick={handleVerifyCognates}>
          Verify Cognates
        </Button>
        <Button size="sm" variant="secondary" onClick={handleFlagBorrowing}>
          Flag Borrowing
        </Button>
        <Button size="sm" variant="secondary" loading={computeState.status === "running"} onClick={handleRunCompute}>
          Run Compute
        </Button>
        <Button size="sm" variant="secondary" loading={exportLoading} onClick={handleExportLingPy}>
          Export LingPy TSV
        </Button>
      </div>

      {computeState.status !== "idle" && (
        <div data-testid="compute-status" style={{ marginTop: "0.5rem", color: "#6b7280", fontSize: "0.75rem" }}>
          {computeState.status === "running" && `Compute running (${Math.round(computeState.progress * 100)}%)`}
          {computeState.status === "complete" && "Compute complete"}
          {computeState.status === "error" && `Compute failed: ${computeState.error ?? "unknown error"}`}
        </div>
      )}
    </div>
  );
}
