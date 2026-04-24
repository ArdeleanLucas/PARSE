import { Fragment, useState } from "react";
import { useConfigStore } from "../../stores/configStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { useUIStore } from "../../stores/uiStore";
import { useEnrichmentStore } from "../../stores/enrichmentStore";
import { useTagStore } from "../../stores/tagStore";
import { Badge } from "../shared/Badge";
import { LexemeDetail } from "./LexemeDetail";

/* ------------------------------------------------------------------ */
/*  Local types                                                        */
/* ------------------------------------------------------------------ */

interface ConceptEntry {
  conceptId: string;
  ipa: string;
  ortho: string;
  sourceWav: string | null;
  startSec: number | null;
  endSec: number | null;
}

interface CognateGroup {
  group: string; // "A"|"B"|"C"|"D"|"E"
  color: string; // hex background
}

export interface ConceptTableProps {
  onPlayEntry?: (
    speaker: string,
    conceptId: string,
    startSec: number,
    endSec: number,
    sourceWav: string,
  ) => void;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const GROUP_COLORS: Record<string, string> = {
  A: "#dcfce7",
  B: "#dbeafe",
  C: "#fef9c3",
  D: "#fce7f3",
  E: "#f3e8ff",
};

const EPS = 0.01;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function normalizeConcept(raw: string): string {
  let s = raw.trim();
  if (s.startsWith("#")) s = s.slice(1);
  const colonIdx = s.indexOf(":");
  if (colonIdx >= 0) s = s.slice(0, colonIdx);
  return s.trim();
}

function parseConcepts(
  concepts: unknown,
): { id: string; label: string }[] {
  if (!Array.isArray(concepts)) return [];
  return concepts.map((c) => {
    if (typeof c === "string") {
      const id = normalizeConcept(c);
      return { id, label: id };
    }
    if (c && typeof c === "object" && ("id" in c || "label" in c)) {
      const obj = c as { id?: string; label?: string };
      const id = normalizeConcept(obj.id ?? obj.label ?? "");
      const label = obj.label ?? obj.id ?? id;
      return { id, label };
    }
    return { id: String(c), label: String(c) };
  });
}

function lookupEntry(
  records: Record<string, unknown>,
  speaker: string,
  conceptId: string,
): ConceptEntry {
  const empty: ConceptEntry = {
    conceptId,
    ipa: "",
    ortho: "",
    sourceWav: null,
    startSec: null,
    endSec: null,
  };

  const rec = records[speaker] as {
    tiers?: Record<
      string,
      { intervals?: { start: number; end: number; text: string }[] }
    >;
    source_wav?: string;
  } | undefined;
  if (!rec?.tiers?.concept?.intervals) return empty;

  const conceptInterval = rec.tiers.concept.intervals.find(
    (iv) => normalizeConcept(iv.text) === conceptId,
  );
  if (!conceptInterval) return empty;

  const { start, end } = conceptInterval;

  const findMatch = (tier: string): string => {
    const intervals = rec.tiers?.[tier]?.intervals;
    if (!intervals) return "";
    const match = intervals.find(
      (iv) =>
        Math.abs(iv.start - start) < EPS && Math.abs(iv.end - end) < EPS,
    );
    return match?.text ?? "";
  };

  return {
    conceptId,
    ipa: findMatch("ipa"),
    ortho: findMatch("ortho"),
    sourceWav: rec.source_wav || null,
    startSec: start,
    endSec: end,
  };
}

function getCognateGroup(
  enrichmentData: Record<string, unknown>,
  conceptId: string,
  speaker: string,
): CognateGroup | null {
  const overrides = enrichmentData?.manual_overrides as
    | { cognate_sets?: Record<string, Record<string, string[]>> }
    | undefined;
  const base = enrichmentData?.cognate_sets as
    | Record<string, Record<string, string[]>>
    | undefined;

  const sets = overrides?.cognate_sets?.[conceptId] ?? base?.[conceptId];
  if (!sets) return null;

  for (const [group, speakers] of Object.entries(sets)) {
    if (Array.isArray(speakers) && speakers.includes(speaker)) {
      const color = GROUP_COLORS[group] ?? "#e5e7eb";
      return { group, color };
    }
  }
  return null;
}

function expandKey(speaker: string, conceptId: string): string {
  return `${speaker}::${conceptId}`;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ConceptTable({ onPlayEntry }: ConceptTableProps) {
  const config = useConfigStore((s) => s.config);
  const records = useAnnotationStore((s) => s.records);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedSpeakers = useUIStore((s) => s.selectedSpeakers);
  const setActiveConcept = useUIStore((s) => s.setActiveConcept);
  const enrichmentData = useEnrichmentStore((s) => s.data);
  const getTagsForConcept = useTagStore((s) => s.getTagsForConcept);
  const getTagsForLexeme = useTagStore((s) => s.getTagsForLexeme);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggleExpanded(speaker: string, conceptId: string) {
    const key = expandKey(speaker, conceptId);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const concepts = parseConcepts(
    (config as Record<string, unknown> | null)?.concepts,
  );
  const speakers =
    selectedSpeakers.length > 0
      ? selectedSpeakers
      : config?.speakers ?? [];

  if (concepts.length === 0) {
    return (
      <div style={{ fontFamily: "monospace", padding: "1rem", color: "#6b7280" }}>
        No concepts loaded.
      </div>
    );
  }

  const totalCols = 1 + speakers.length;

  return (
    <div style={{ fontFamily: "monospace", overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.8125rem",
        }}
      >
        <thead>
          <tr>
            <th
              style={{
                textAlign: "left",
                padding: "0.5rem",
                borderBottom: "2px solid #e5e7eb",
                whiteSpace: "nowrap",
              }}
            >
              Concept
            </th>
            {speakers.map((sp) => (
              <th
                key={sp}
                style={{
                  textAlign: "left",
                  padding: "0.5rem",
                  borderBottom: "2px solid #e5e7eb",
                  whiteSpace: "nowrap",
                }}
              >
                {sp}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {concepts.map((concept, idx) => {
            const isActive = activeConcept === concept.id;
            const conceptTags = getTagsForConcept(concept.id);
            const expandedSpeakers = speakers.filter((sp) =>
              expanded.has(expandKey(sp, concept.id)),
            );

            return (
              <Fragment key={concept.id}>
                <tr
                  data-testid={`concept-row-${concept.id}`}
                  onClick={() => setActiveConcept(concept.id)}
                  style={{
                    cursor: "pointer",
                    background: isActive ? "#eff6ff" : undefined,
                    borderLeft: isActive
                      ? "3px solid #3b82f6"
                      : "3px solid transparent",
                  }}
                >
                  <td
                    style={{
                      padding: "0.5rem",
                      borderBottom: "1px solid #f3f4f6",
                      verticalAlign: "top",
                    }}
                  >
                    <div>
                      #{idx + 1} {concept.label}
                    </div>
                    {conceptTags.length > 0 && (
                      <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                        {conceptTags.map((tag) => (
                          <Badge key={tag.id} label={tag.label} color={tag.color} />
                        ))}
                      </div>
                    )}
                  </td>
                  {speakers.map((sp) => {
                    const entry = lookupEntry(records, sp, concept.id);
                    const cognate = getCognateGroup(
                      enrichmentData,
                      concept.id,
                      sp,
                    );
                    const hasForm = entry.ipa || entry.ortho;
                    const key = expandKey(sp, concept.id);
                    const isExpanded = expanded.has(key);
                    const lexTags = getTagsForLexeme(sp, concept.id);

                    return (
                      <td
                        key={sp}
                        style={{
                          padding: "0.5rem",
                          borderBottom: "1px solid #f3f4f6",
                          verticalAlign: "top",
                          background: isExpanded ? "#eef2ff" : undefined,
                        }}
                      >
                        {hasForm ? (
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                              {cognate && (
                                <span
                                  data-testid={`cognate-badge-${concept.id}-${sp}`}
                                  style={{
                                    display: "inline-block",
                                    padding: "0 0.375rem",
                                    borderRadius: "0.25rem",
                                    fontSize: "0.6875rem",
                                    fontWeight: 600,
                                    background: cognate.color,
                                  }}
                                >
                                  {cognate.group}
                                </span>
                              )}
                              <button
                                data-testid={`lexeme-button-${concept.id}-${sp}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleExpanded(sp, concept.id);
                                }}
                                title="Click to expand lexeme details"
                                style={{
                                  background: "none",
                                  border: "none",
                                  padding: 0,
                                  cursor: "pointer",
                                  color: "#1d4ed8",
                                  textDecoration: "underline",
                                  textUnderlineOffset: "2px",
                                  font: "inherit",
                                }}
                              >
                                {entry.ipa}
                              </button>
                              {entry.startSec != null &&
                                entry.endSec != null &&
                                entry.sourceWav && (
                                  <button
                                    aria-label={`Play ${sp} ${concept.id}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onPlayEntry?.(
                                        sp,
                                        concept.id,
                                        entry.startSec!,
                                        entry.endSec!,
                                        entry.sourceWav!,
                                      );
                                    }}
                                    style={{
                                      background: "none",
                                      border: "1px solid #d1d5db",
                                      borderRadius: "0.25rem",
                                      cursor: "pointer",
                                      padding: "0 0.25rem",
                                      fontSize: "0.6875rem",
                                      fontFamily: "monospace",
                                      lineHeight: 1.4,
                                    }}
                                  >
                                    ▶
                                  </button>
                                )}
                            </div>
                            {entry.ortho && (
                              <div style={{ color: "#6b7280", fontSize: "0.75rem" }}>
                                {entry.ortho}
                              </div>
                            )}
                            {lexTags.length > 0 && (
                              <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                                {lexTags.map((tag) => (
                                  <Badge key={tag.id} label={tag.label} color={tag.color} />
                                ))}
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: "#9ca3af", fontStyle: "italic" }}>
                            No form
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
                {expandedSpeakers.length > 0 && (
                  <tr data-testid={`detail-row-${concept.id}`}>
                    <td
                      colSpan={totalCols}
                      style={{
                        padding: "0.25rem 0.5rem 0.75rem 0.5rem",
                        borderBottom: "1px solid #f3f4f6",
                        background: "#f9fafb",
                      }}
                    >
                      {expandedSpeakers.map((sp) => {
                        const entry = lookupEntry(records, sp, concept.id);
                        const cognate = getCognateGroup(
                          enrichmentData,
                          concept.id,
                          sp,
                        );
                        return (
                          <LexemeDetail
                            key={expandKey(sp, concept.id)}
                            speaker={sp}
                            conceptId={concept.id}
                            conceptLabel={concept.label}
                            ipa={entry.ipa}
                            ortho={entry.ortho}
                            startSec={entry.startSec}
                            endSec={entry.endSec}
                            cognateGroup={cognate?.group ?? null}
                            cognateColor={cognate?.color ?? null}
                          />
                        );
                      })}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
