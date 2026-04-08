import { useState, useEffect, useCallback } from "react";
import { useUIStore } from "../../stores/uiStore";
import { usePlaybackStore } from "../../stores/playbackStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import { Button } from "../shared/Button";
import { Input } from "../shared/Input";
import type { AnnotationInterval } from "../../api/types";

interface AnnotationPanelProps {
  onAnnotationSaved?: (speaker: string, tier: string, interval: AnnotationInterval) => void;
}

const EPSILON = 0.0005;

function overlaps(
  iv: AnnotationInterval,
  region: { start: number; end: number } | null,
): boolean {
  if (!region) return false;
  return (
    iv.start <= region.end + EPSILON && iv.end >= region.start - EPSILON
  );
}

export function AnnotationPanel({ onAnnotationSaved }: AnnotationPanelProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedRegion = usePlaybackStore((s) => s.selectedRegion);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? (s.records[activeSpeaker] ?? null) : null,
  );
  const addInterval = useAnnotationStore((s) => s.addInterval);
  const removeInterval = useAnnotationStore((s) => s.removeInterval);

  const [ipa, setIpa] = useState("");
  const [ortho, setOrtho] = useState("");
  const [concept, setConcept] = useState("");
  const [feedback, setFeedback] = useState("");
  const [feedbackIsError, setFeedbackIsError] = useState(false);

  useEffect(() => {
    setIpa("");
    setOrtho("");
    setConcept(activeConcept ?? "");
    setFeedback("");
    setFeedbackIsError(false);
  }, [activeSpeaker, activeConcept]);

  const saveDisabled =
    !activeSpeaker || !activeConcept || !selectedRegion || (!ipa.trim() && !ortho.trim());

  const handleSave = useCallback(() => {
    if (!activeSpeaker || !selectedRegion) return;

    const { start, end } = selectedRegion;
    const fields: [string, string][] = [
      ["ipa", ipa.trim()],
      ["ortho", ortho.trim()],
      ["concept", concept.trim()],
    ];

    let savedIpaInterval: AnnotationInterval | null = null;
    for (const [tier, text] of fields) {
      if (text) {
        const interval: AnnotationInterval = { start, end, text };
        addInterval(activeSpeaker, tier, interval);
        if (tier === "ipa") savedIpaInterval = interval;
      }
    }

    setIpa("");
    setOrtho("");
    setConcept("");
    setFeedback("Saved.");
    setFeedbackIsError(false);

    if (savedIpaInterval) {
      onAnnotationSaved?.(activeSpeaker, "ipa", savedIpaInterval);
    }
  }, [activeSpeaker, selectedRegion, ipa, ortho, concept, addInterval, onAnnotationSaved]);

  const handleClear = useCallback(() => {
    setIpa("");
    setOrtho("");
    setConcept(activeConcept ?? "");
    setFeedback("");
    setFeedbackIsError(false);
  }, [activeConcept]);

  const ipaIntervals = record?.tiers?.ipa?.intervals ?? [];

  return (
    <div
      style={{
        border: "1px solid #d6e0ea",
        borderRadius: "0.25rem",
        background: "#f6f9fc",
        fontFamily: "monospace",
        fontSize: "0.875rem",
        padding: "0.75rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.625rem",
      }}
    >
      {/* Header */}
      <div style={{ fontWeight: 600 }}>
        Annotation — {activeSpeaker ?? "No speaker"} / concept #
        {activeConcept ?? "none"}
      </div>
      <div style={{ color: "#6b7280" }}>
        {selectedRegion
          ? `Region: ${selectedRegion.start.toFixed(3)} s \u2013 ${selectedRegion.end.toFixed(3)} s`
          : "No region selected"}
      </div>

      {/* Inputs */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          borderTop: "1px solid #d6e0ea",
          paddingTop: "0.5rem",
        }}
      >
        <Input label="IPA" value={ipa} onChange={(e) => setIpa(e.target.value)} />
        <Input label="Ortho" value={ortho} onChange={(e) => setOrtho(e.target.value)} />
        <Input label="Concept" value={concept} onChange={(e) => setConcept(e.target.value)} />
      </div>

      {/* Actions */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          borderTop: "1px solid #d6e0ea",
          paddingTop: "0.5rem",
          alignItems: "center",
        }}
      >
        <Button variant="primary" disabled={saveDisabled} onClick={handleSave}>
          Save annotation
        </Button>
        <Button variant="secondary" onClick={handleClear}>
          Clear
        </Button>
      </div>
      {feedback && (
        <div style={{ color: feedbackIsError ? "#ef4444" : "#16a34a", fontSize: "0.75rem" }}>
          {feedback}
        </div>
      )}

      {/* Existing annotations */}
      <div
        style={{
          borderTop: "1px solid #d6e0ea",
          paddingTop: "0.5rem",
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
          Existing annotations
        </div>
        {ipaIntervals.length === 0 ? (
          <div style={{ color: "#9ca3af" }}>No annotations yet.</div>
        ) : (
          ipaIntervals.map((iv, idx) => {
            const active = overlaps(iv, selectedRegion);
            return (
              <div
                key={`${iv.start}-${iv.end}-${idx}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.25rem 0",
                  background: active ? "rgba(33, 94, 191, 0.08)" : "transparent",
                  borderLeft: active ? "2px solid #215ebf" : "2px solid transparent",
                  paddingLeft: "0.375rem",
                }}
              >
                <span>
                  {iv.start.toFixed(3)} &ndash; {iv.end.toFixed(3)}{" "}
                  <span style={{ color: "#215ebf" }}>{iv.text}</span>
                </span>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    if (activeSpeaker) removeInterval(activeSpeaker, "ipa", idx);
                  }}
                >
                  Delete
                </Button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
