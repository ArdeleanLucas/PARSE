import React, { useState, useEffect, useCallback } from "react";
import { useUIStore } from "../../stores/uiStore";
import { usePlaybackStore } from "../../stores/playbackStore";
import { LEGACY_ANNOTATE_REGION_STORAGE_KEY } from "../../lib/decisionPersistence";
import { Button } from "../shared/Button";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Decision {
  source_wav: string | null;
  start_sec: number;
  end_sec: number;
  assigned: boolean;
  replaces_segment: boolean;
  notes?: string;
  ai_suggestion_used?: boolean;
  ai_suggestion_confidence?: number;
  ai_suggestion_score?: number;
}

interface ActiveSuggestion {
  suggestionIndex: number | null;
  segmentStartSec: number | null;
  segmentEndSec: number | null;
  score: number | null;
}

export interface RegionManagerProps {
  onSeek: (timeSec: number, createRegion?: boolean, regionDurationSec?: number) => void;
  onAssigned?: (speaker: string, conceptId: string, startSec: number, endSec: number) => void;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

type DecisionsMap = Record<string, Record<string, Decision>>;

// Annotate-only convenience state: prior manually assigned regions for the
// waveform review workflow. This is intentionally local-only and segregated
// from the compare-mode canonical `parse-decisions/v1` artifact.
function loadLegacyRegionAssignments(): DecisionsMap {
  try {
    const raw = localStorage.getItem(LEGACY_ANNOTATE_REGION_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveLegacyRegionAssignments(decisions: DecisionsMap) {
  try {
    localStorage.setItem(LEGACY_ANNOTATE_REGION_STORAGE_KEY, JSON.stringify(decisions));
  } catch {
    /* ignore */
  }
}

function round3(n: number): number {
  return Math.round(n * 1000) / 1000;
}

function formatSec(t: number): string {
  return t.toFixed(3) + " s";
}

/* ------------------------------------------------------------------ */
/*  Styles                                                             */
/* ------------------------------------------------------------------ */

const rootStyle: React.CSSProperties = {
  border: "1px solid #d7dee8",
  borderRadius: 10,
  padding: 12,
  background: "#f8fafc",
  display: "flex",
  flexDirection: "column",
  gap: 10,
  fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  fontSize: 14,
  lineHeight: 1.45,
  color: "#1f2937",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  flexWrap: "wrap",
};

const cardStyle: React.CSSProperties = {
  padding: 10,
  borderRadius: 8,
  background: "#fff",
  border: "1px solid #e2e8f0",
};

const suggestionCardStyle: React.CSSProperties = {
  ...cardStyle,
  background: "#fff7ed",
  borderColor: "#fed7aa",
  color: "#9a3412",
};

const buttonRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
  alignItems: "center",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function RegionManager({ onSeek, onAssigned }: RegionManagerProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedRegion = usePlaybackStore((s) => s.selectedRegion);

  const [feedback, setFeedback] = useState("");
  const [feedbackIsError, setFeedbackIsError] = useState(false);
  const [priorDecision, setPriorDecision] = useState<Decision | null>(null);
  const [activeSuggestion, setActiveSuggestion] = useState<ActiveSuggestion | null>(null);

  // Reset on context change
  useEffect(() => {
    setActiveSuggestion(null);
    setFeedback("");
    setFeedbackIsError(false);

    if (!activeSpeaker || !activeConcept) {
      setPriorDecision(null);
      return;
    }

    const decisions = loadLegacyRegionAssignments();
    const conceptDecisions = decisions[activeConcept];
    const prior = conceptDecisions?.[activeSpeaker] ?? null;
    setPriorDecision(prior);
  }, [activeSpeaker, activeConcept]);

  const handleLoadPrior = useCallback(() => {
    if (!priorDecision) return;
    const duration = Math.max(0.05, priorDecision.end_sec - priorDecision.start_sec);
    onSeek(priorDecision.start_sec, true, duration);
    setFeedback("Loaded prior region into the waveform.");
    setFeedbackIsError(false);
  }, [priorDecision, onSeek]);

  const handleAssign = useCallback(() => {
    if (!activeSpeaker || !activeConcept || !selectedRegion) return;

    const decisions = loadLegacyRegionAssignments();
    const start = round3(selectedRegion.start);
    const end = round3(selectedRegion.end);

    const newDecision: Decision = {
      source_wav: null,
      start_sec: start,
      end_sec: end,
      assigned: true,
      replaces_segment: true,
    };

    if (!decisions[activeConcept]) {
      decisions[activeConcept] = {};
    }
    decisions[activeConcept][activeSpeaker] = newDecision;
    saveLegacyRegionAssignments(decisions);

    setPriorDecision(newDecision);
    setFeedback(`Assigned ${formatSec(start)}\u2013${formatSec(end)} to concept #${activeConcept}.`);
    setFeedbackIsError(false);

    onAssigned?.(activeSpeaker, activeConcept, start, end);
  }, [activeSpeaker, activeConcept, selectedRegion, onAssigned]);

  // Derive status text
  const statusText =
    activeSpeaker && activeConcept
      ? `${activeSpeaker} \u00b7 concept #${activeConcept}`
      : "No active context.";

  const canAssign = !!(activeSpeaker && activeConcept && selectedRegion);
  const canLoadPrior = !!priorDecision;

  return (
    <section aria-label="Region assignment controls" style={rootStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>Region assignment</div>
        <div style={{ fontSize: 12, color: "#475569" }}>{statusText}</div>
      </div>

      {/* Current region */}
      <div style={cardStyle}>
        <div style={{ fontWeight: 600 }}>Current region</div>
        <div style={{ marginTop: 4, color: "#64748b" }}>
          {selectedRegion
            ? `${formatSec(selectedRegion.start)} \u2013 ${formatSec(selectedRegion.end)}`
            : "No region selected"}
        </div>
      </div>

      {/* Suggestion banner */}
      {activeSuggestion && (
        <div style={suggestionCardStyle}>
          <div style={{ fontWeight: 600 }}>AI suggestion attached</div>
          {activeSuggestion.score != null && (
            <div style={{ marginTop: 4 }}>Score: {activeSuggestion.score.toFixed(2)}</div>
          )}
        </div>
      )}

      {/* Prior assignment */}
      <div style={cardStyle}>
        <div style={{ fontWeight: 600 }}>Prior assignment</div>
        <div style={{ marginTop: 4, color: "#64748b" }}>
          {priorDecision
            ? `${formatSec(priorDecision.start_sec)} \u2013 ${formatSec(priorDecision.end_sec)}`
            : "None"}
        </div>
      </div>

      {/* Buttons */}
      <div style={buttonRowStyle}>
        <Button variant="secondary" size="sm" disabled={!canLoadPrior} onClick={handleLoadPrior}>
          Load prior region
        </Button>
        <Button variant="primary" size="sm" disabled={!canAssign} onClick={handleAssign}>
          Assign to concept
        </Button>
      </div>

      {/* Feedback */}
      {feedback && (
        <div style={{ fontSize: 12, color: feedbackIsError ? "#b91c1c" : "#475569" }}>
          {feedback}
        </div>
      )}
    </section>
  );
}
