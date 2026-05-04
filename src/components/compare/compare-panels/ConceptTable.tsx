import { useState } from "react";
import { useTagStore } from "../../../stores/tagStore";
import type { Tag } from "../../../api/types";
import { useCompareSelection } from "./useCompareSelection";
import { parseConcepts } from "./shared";
import { ConceptRow } from "./ConceptRow";
import type { ConceptTableProps } from "./types";

export function ConceptTable({ onPlayEntry }: ConceptTableProps) {
  const { activeConcept, config, enrichmentData, records, setActiveConcept, speakers } = useCompareSelection();
  const tags = useTagStore((s) => s.tags);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpanded = (speaker: string, conceptId: string) => {
    const key = `${speaker}::${conceptId}`;
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const concepts = parseConcepts((config as Record<string, unknown> | null)?.concepts);
  const tagsById = new Map(tags.map((tag) => [tag.id, tag]));
  const getTagsForConcept = (conceptId: string): Tag[] => {
    const ids = new Set<string>();
    for (const record of Object.values(records)) {
      for (const tagId of record.concept_tags?.[conceptId] ?? []) ids.add(tagId);
    }
    return Array.from(ids).map((id) => tagsById.get(id)).filter((tag): tag is Tag => Boolean(tag));
  };
  const getTagsForLexeme = (speaker: string, conceptId: string): Tag[] => {
    const ids = records[speaker]?.concept_tags?.[conceptId] ?? [];
    return ids.map((id) => tagsById.get(id)).filter((tag): tag is Tag => Boolean(tag));
  };
  if (concepts.length === 0) {
    return <div style={{ fontFamily: "monospace", padding: "1rem", color: "#6b7280" }}>No concepts loaded.</div>;
  }

  const totalCols = 1 + speakers.length;
  return (
    <div style={{ fontFamily: "monospace", overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "0.5rem", borderBottom: "2px solid #e5e7eb", whiteSpace: "nowrap" }}>Concept</th>
            {speakers.map((speaker) => (
              <th key={speaker} style={{ textAlign: "left", padding: "0.5rem", borderBottom: "2px solid #e5e7eb", whiteSpace: "nowrap" }}>{speaker}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {concepts.map((concept, index) => (
            <ConceptRow
              key={concept.id}
              concept={concept}
              index={index}
              speakers={speakers}
              activeConcept={activeConcept}
              records={records}
              enrichmentData={enrichmentData}
              expanded={expanded}
              toggleExpanded={toggleExpanded}
              setActiveConcept={setActiveConcept}
              getTagsForConcept={getTagsForConcept}
              getTagsForLexeme={getTagsForLexeme}
              totalCols={totalCols}
              onPlayEntry={onPlayEntry}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
