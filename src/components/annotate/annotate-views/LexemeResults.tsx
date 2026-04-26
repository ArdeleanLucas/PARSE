import { Button } from "../../shared/Button";
import type { LexemeSearchCandidate, LexemeSearchResponse } from "../../../api/client";

import { formatSearchTime, tierChipBg } from "./shared";

interface LexemeResultsProps {
  candidates: LexemeSearchCandidate[];
  onConfirm: (candidate: LexemeSearchCandidate) => void;
  onSeek?: (timeSec: number) => void;
  response: LexemeSearchResponse | null;
  selectedKey: string | null;
  setSelectedKey: (key: string) => void;
  keyOf: (candidate: LexemeSearchCandidate) => string;
}

export function LexemeResults({
  candidates,
  onConfirm,
  onSeek,
  response,
  selectedKey,
  setSelectedKey,
  keyOf,
}: LexemeResultsProps) {
  if (candidates.length === 0) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.25rem" }}>
      <div style={{ fontSize: "0.7rem", fontWeight: 600, color: "#1e3a8a", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Candidates
      </div>
      {candidates.map((candidate) => {
        const key = keyOf(candidate);
        const isSelected = selectedKey === key;
        return (
          <div
            key={key}
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr auto auto",
              gap: "0.5rem",
              alignItems: "center",
              padding: "0.375rem 0.5rem",
              borderRadius: "0.25rem",
              border: `1px solid ${isSelected ? "#1d4ed8" : "#cbd5e1"}`,
              background: isSelected ? "#dbeafe" : "#ffffff",
              fontFamily: "monospace",
              fontSize: "0.75rem",
            }}
          >
            <button
              type="button"
              onClick={() => {
                setSelectedKey(key);
                onSeek?.(candidate.start);
              }}
              style={{
                background: "transparent",
                border: 0,
                padding: 0,
                color: "#475569",
                cursor: "pointer",
                fontFamily: "monospace",
                fontSize: "0.75rem",
              }}
              title="Click to seek the waveform here"
            >
              {formatSearchTime(candidate.start)}–{formatSearchTime(candidate.end)}
            </button>
            <span
              style={{
                color: "#0f172a",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={`Phonetic ${candidate.phonetic_score.toFixed(3)}, cross-speaker bonus ${candidate.cross_speaker_score.toFixed(3)}, confidence ${candidate.confidence_weight.toFixed(2)}`}
            >
              {candidate.matched_text}
            </span>
            <span
              style={{
                fontSize: "0.65rem",
                padding: "0.125rem 0.375rem",
                borderRadius: "999px",
                background: tierChipBg(candidate.tier),
                color: "#fff",
                whiteSpace: "nowrap",
              }}
            >
              {candidate.source_label}
            </span>
            <Button
              variant="primary"
              size="sm"
              onClick={() => onConfirm(candidate)}
              title="Save this time range as the confirmed anchor for this concept on this speaker."
            >
              Confirm
            </Button>
          </div>
        );
      })}

      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          alignItems: "center",
          borderTop: "1px solid #bfdbfe",
          paddingTop: "0.5rem",
          marginTop: "0.25rem",
        }}
      >
        <Button
          variant="secondary"
          size="sm"
          disabled={true}
          title="Coming in PR C — confirm a few anchors first, then bulk-align the remaining concepts for this speaker using the confirmed anchors as scaffolding."
        >
          Bulk align remaining (coming in PR C)
        </Button>
        {response?.signals_available && (
          <span style={{ fontSize: "0.7rem", color: "#64748b", marginLeft: "auto" }}>
            phonemizer {response.signals_available.phonemizer ? "✓" : "—"} · cross-speaker anchors {response.signals_available.cross_speaker_anchors}
          </span>
        )}
      </div>
    </div>
  );
}
