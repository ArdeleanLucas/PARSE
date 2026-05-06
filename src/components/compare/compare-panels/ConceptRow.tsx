import { Badge } from "../../shared/Badge";
import { LexemeDetail } from "./LexemeDetail";
import { expandKey, getCognateGroup, lookupEntry } from "./shared";
import type { ConceptRowProps } from "./types";

export function ConceptRow({
  concept,
  index,
  speakers,
  activeConcept,
  records,
  enrichmentData,
  expanded,
  toggleExpanded,
  setActiveConcept,
  getTagsForConcept,
  getTagsForLexeme,
  totalCols,
  onPlayEntry,
}: ConceptRowProps) {
  const rawConceptId = concept.key ?? concept.id;
  const isActive = activeConcept === concept.id;
  const conceptTags = getTagsForConcept(concept.id);
  const expandedSpeakers = speakers.filter((speaker) => expanded.has(expandKey(speaker, concept.id)));

  return (
    <>
      <tr
        data-testid={`concept-row-${concept.id}`}
        onClick={() => setActiveConcept(concept.id)}
        style={{
          cursor: "pointer",
          background: isActive ? "#eff6ff" : undefined,
          borderLeft: isActive ? "3px solid #3b82f6" : "3px solid transparent",
        }}
      >
        <td style={{ padding: "0.5rem", borderBottom: "1px solid #f3f4f6", verticalAlign: "top" }}>
          <div>#{index + 1} {concept.label}</div>
          {conceptTags.length > 0 && (
            <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
              {conceptTags.map((tag) => <Badge key={tag.id} label={tag.label} color={tag.color} />)}
            </div>
          )}
        </td>
        {speakers.map((speaker) => {
          const entry = lookupEntry(records, speaker, concept.id);
          const cognate = getCognateGroup(enrichmentData, concept.id, speaker);
          const hasForm = entry.ipa || entry.ortho;
          const key = expandKey(speaker, concept.id);
          const isExpanded = expanded.has(key);
          const lexTags = getTagsForLexeme(speaker, concept.id);
          return (
            <td
              key={speaker}
              style={{ padding: "0.5rem", borderBottom: "1px solid #f3f4f6", verticalAlign: "top", background: isExpanded ? "#eef2ff" : undefined }}
            >
              {hasForm ? (
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                    {cognate && (
                      <span
                        data-testid={`cognate-badge-${concept.id}-${speaker}`}
                        style={{ display: "inline-block", padding: "0 0.375rem", borderRadius: "0.25rem", fontSize: "0.6875rem", fontWeight: 600, background: cognate.color }}
                      >
                        {cognate.group}
                      </span>
                    )}
                    <button
                      data-testid={`lexeme-button-${concept.id}-${speaker}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleExpanded(speaker, concept.id);
                      }}
                      title="Click to expand lexeme details"
                      style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "#1d4ed8", textDecoration: "underline", textUnderlineOffset: "2px", font: "inherit" }}
                    >
                      {entry.ipa}
                    </button>
                    {entry.startSec != null && entry.endSec != null && entry.sourceWav && (
                      <button
                        aria-label={`Play ${speaker} ${concept.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onPlayEntry?.(speaker, concept.id, entry.startSec!, entry.endSec!, entry.sourceWav!);
                        }}
                        style={{ background: "none", border: "1px solid #d1d5db", borderRadius: "0.25rem", cursor: "pointer", padding: "0 0.25rem", fontSize: "0.6875rem", fontFamily: "monospace", lineHeight: 1.4 }}
                      >
                        ▶
                      </button>
                    )}
                  </div>
                  {entry.ortho && <div style={{ color: "#6b7280", fontSize: "0.75rem" }}>{entry.ortho}</div>}
                  {lexTags.length > 0 && (
                    <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                      {lexTags.map((tag) => <Badge key={tag.id} label={tag.label} color={tag.color} />)}
                    </div>
                  )}
                </div>
              ) : (
                <span style={{ color: "#9ca3af", fontStyle: "italic" }}>No form</span>
              )}
            </td>
          );
        })}
      </tr>
      {expandedSpeakers.length > 0 && (
        <tr data-testid={`detail-row-${concept.id}`}>
          <td colSpan={totalCols} style={{ padding: "0.25rem 0.5rem 0.75rem 0.5rem", borderBottom: "1px solid #f3f4f6", background: "#f9fafb" }}>
            {expandedSpeakers.map((speaker) => {
              const entry = lookupEntry(records, speaker, concept.id);
              const cognate = getCognateGroup(enrichmentData, concept.id, speaker);
              return (
                <LexemeDetail
                  key={expandKey(speaker, concept.id)}
                  speaker={speaker}
                  conceptId={rawConceptId}
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
    </>
  );
}
