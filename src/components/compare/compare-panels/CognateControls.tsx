import { useMemo } from "react";
import { useCompareSelection } from "./useCompareSelection";
import { useEnrichmentsBinding } from "./useEnrichmentsBinding";
import { useCognateDecisions } from "./useCognateDecisions";
import { CognateActionMenu } from "./CognateActionMenu";
import type { CognateControlsProps } from "./types";

export function CognateControls({ onGroupsChanged }: CognateControlsProps) {
  const { activeConcept, config, records, selectedSpeakers } = useCompareSelection();
  const { enrichmentData, saveEnrichments } = useEnrichmentsBinding();
  const allSpeakers = useMemo(
    () => (selectedSpeakers.length > 0 ? selectedSpeakers : config?.speakers ?? []),
    [config?.speakers, selectedSpeakers],
  );
  const {
    findSpeakerGroup,
    handleAccept,
    handleCycleClick,
    handleCycleToggle,
    handleDoneSplit,
    handleMerge,
    handleSplitMove,
    handleSplitToggle,
    mode,
    setSplitTarget,
    speakersWithForm,
    splitTarget,
  } = useCognateDecisions({
    activeConcept,
    allSpeakers,
    enrichmentData,
    records,
    save: saveEnrichments,
    onGroupsChanged,
  });

  if (!activeConcept) {
    return <div style={{ fontFamily: "monospace", padding: "1rem", color: "#6b7280" }}>Select a concept in the table.</div>;
  }

  return (
    <div style={{ fontFamily: "monospace", padding: "1rem" }}>
      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Cognate Controls</div>
      <div style={{ marginBottom: "0.5rem", color: "#374151" }}>Concept: {activeConcept}</div>

      <CognateActionMenu
        mode={mode}
        splitTarget={splitTarget}
        setSplitTarget={setSplitTarget}
        handleAccept={handleAccept}
        handleMerge={handleMerge}
        handleSplitToggle={handleSplitToggle}
        handleCycleToggle={handleCycleToggle}
        handleDoneSplit={handleDoneSplit}
      />

      <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
        {allSpeakers.map((speaker) => {
          const hasForm = speakersWithForm.includes(speaker);
          const groupLetter = findSpeakerGroup(speaker);
          const handleClick = () => {
            if (!hasForm) return;
            if (mode === "split") handleSplitMove(speaker);
            else if (mode === "cycle") void handleCycleClick(speaker);
          };
          return (
            <button
              key={speaker}
              data-testid={`speaker-btn-${speaker}`}
              disabled={!hasForm}
              onClick={handleClick}
              style={{
                padding: "0.25rem 0.625rem",
                borderRadius: "0.25rem",
                border: "1px solid #d1d5db",
                background: groupLetter ? ({ A: "#dcfce7", B: "#dbeafe", C: "#fef9c3", D: "#fce7f3", E: "#f3e8ff" }[groupLetter] ?? "#e5e7eb") : "#f9fafb",
                cursor: hasForm ? "pointer" : "not-allowed",
                opacity: hasForm ? 1 : 0.5,
                fontFamily: "monospace",
                fontSize: "0.75rem",
              }}
            >
              {speaker}: {groupLetter ?? "–"}
            </button>
          );
        })}
      </div>
    </div>
  );
}
