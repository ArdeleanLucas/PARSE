import { useState, useEffect, useCallback, useMemo } from "react";
import { useUIStore } from "../../stores/uiStore";
import { usePlaybackStore } from "../../stores/playbackStore";
import { useAnnotationStore } from "../../stores/annotationStore";
import {
  useTranscriptionLanesStore,
  LANE_LABELS,
} from "../../stores/transcriptionLanesStore";
import { Button } from "../shared/Button";
import { Input } from "../shared/Input";
import { LexemeSearchPanel } from "./LexemeSearchPanel";
import type { AnnotationInterval } from "../../api/types";

interface AnnotationPanelProps {
  onAnnotationSaved?: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  /** Seek the waveform to a time in seconds. Wired through to
   * LexemeSearchPanel so clicking a candidate jumps playback there. */
  onSeek?: (timeSec: number) => void;
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

export function AnnotationPanel({ onAnnotationSaved, onSeek }: AnnotationPanelProps) {
  const activeSpeaker = useUIStore((s) => s.activeSpeaker);
  const activeConcept = useUIStore((s) => s.activeConcept);
  const selectedRegion = usePlaybackStore((s) => s.selectedRegion);
  const currentTime = usePlaybackStore((s) => s.currentTime);
  const record = useAnnotationStore((s) =>
    activeSpeaker ? (s.records[activeSpeaker] ?? null) : null,
  );
  const addInterval = useAnnotationStore((s) => s.addInterval);
  const removeInterval = useAnnotationStore((s) => s.removeInterval);
  const updateInterval = useAnnotationStore((s) => s.updateInterval);
  const updateIntervalTimes = useAnnotationStore((s) => s.updateIntervalTimes);
  const mergeIntervals = useAnnotationStore((s) => s.mergeIntervals);
  const splitInterval = useAnnotationStore((s) => s.splitInterval);
  const selectedInterval = useTranscriptionLanesStore((s) => s.selectedInterval);
  const setSelectedInterval = useTranscriptionLanesStore((s) => s.setSelectedInterval);

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

      {/* Lexeme search — scaffold half of the Lexical Anchor Alignment
          System. Jumps the waveform to ranked candidate time ranges based
          on fuzzy matches across the loaded tiers. Highest-leverage step
          for the first-word anchoring workflow. */}
      <LexemeSearchPanel onSeek={onSeek} />

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

      {/* Segment controls — visible when a lane interval is selected */}
      <SegmentControls
        speaker={activeSpeaker}
        currentTime={currentTime}
        selected={
          selectedInterval && selectedInterval.speaker === activeSpeaker
            ? selectedInterval
            : null
        }
        record={record}
        onUpdateText={updateInterval}
        onUpdateTimes={updateIntervalTimes}
        onMerge={mergeIntervals}
        onSplit={splitInterval}
        onDelete={(tier, index) => {
          if (!activeSpeaker) return;
          removeInterval(activeSpeaker, tier, index);
          setSelectedInterval(null);
        }}
        onClearSelection={() => setSelectedInterval(null)}
      />

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

interface SegmentControlsProps {
  speaker: string | null;
  currentTime: number;
  selected: { speaker: string; tier: import("../../stores/transcriptionLanesStore").LaneKind; index: number } | null;
  record: import("../../api/types").AnnotationRecord | null;
  onUpdateText: (speaker: string, tier: string, index: number, text: string) => void;
  onUpdateTimes: (speaker: string, tier: string, index: number, start: number, end: number) => void;
  onMerge: (speaker: string, tier: string, index: number) => void;
  onSplit: (speaker: string, tier: string, index: number, splitTime: number) => void;
  onDelete: (tier: string, index: number) => void;
  onClearSelection: () => void;
}

/** Toolbar that operates on the lane-selected interval. Lets the user retime
 * via numeric inputs, retext, merge with the next interval, split at the
 * playhead, or delete. Hidden until an interval is selected. */
function SegmentControls({
  speaker,
  currentTime,
  selected,
  record,
  onUpdateText,
  onUpdateTimes,
  onMerge,
  onSplit,
  onDelete,
  onClearSelection,
}: SegmentControlsProps) {
  const tierData = selected && record?.tiers?.[selected.tier];
  const interval = tierData?.intervals?.[selected?.index ?? -1] ?? null;

  const [startStr, setStartStr] = useState("");
  const [endStr, setEndStr] = useState("");
  const [textStr, setTextStr] = useState("");

  useEffect(() => {
    if (interval) {
      setStartStr(interval.start.toFixed(3));
      setEndStr(interval.end.toFixed(3));
      setTextStr(interval.text);
    }
  }, [interval?.start, interval?.end, interval?.text]);

  const canMerge = useMemo(() => {
    if (!selected || !tierData) return false;
    return selected.index + 1 < tierData.intervals.length;
  }, [selected, tierData]);

  const canSplit = useMemo(() => {
    if (!interval) return false;
    return currentTime > interval.start + 0.001 && currentTime < interval.end - 0.001;
  }, [interval, currentTime]);

  if (!selected || !speaker || !interval) return null;

  const commitTimes = () => {
    const s = parseFloat(startStr);
    const e = parseFloat(endStr);
    if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) {
      // revert visually on invalid input
      setStartStr(interval.start.toFixed(3));
      setEndStr(interval.end.toFixed(3));
      return;
    }
    if (Math.abs(s - interval.start) < 0.0001 && Math.abs(e - interval.end) < 0.0001) return;
    onUpdateTimes(speaker, selected.tier, selected.index, s, e);
  };

  const commitText = () => {
    const trimmed = textStr.trim();
    if (trimmed === interval.text) return;
    onUpdateText(speaker, selected.tier, selected.index, trimmed);
  };

  return (
    <div
      style={{
        borderTop: "1px solid #d6e0ea",
        paddingTop: "0.5rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontWeight: 600 }}>
          Selected segment
          <span style={{ color: "#6b7280", fontWeight: 400, marginLeft: "0.5rem" }}>
            ({LANE_LABELS[selected.tier]} #{selected.index + 1})
          </span>
        </div>
        <Button variant="secondary" size="sm" onClick={onClearSelection}>
          Deselect
        </Button>
      </div>

      <Input
        label="Text"
        value={textStr}
        onChange={(e) => setTextStr(e.target.value)}
        onBlur={commitText}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commitText();
          }
        }}
      />

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <Input
          label="Start (s)"
          type="number"
          step="0.001"
          min="0"
          value={startStr}
          onChange={(e) => setStartStr(e.target.value)}
          onBlur={commitTimes}
        />
        <Input
          label="End (s)"
          type="number"
          step="0.001"
          min="0"
          value={endStr}
          onChange={(e) => setEndStr(e.target.value)}
          onBlur={commitTimes}
        />
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <Button
          variant="secondary"
          size="sm"
          disabled={!canSplit}
          title={
            canSplit
              ? `Split at playhead (${currentTime.toFixed(3)} s)`
              : "Move the playhead inside the segment to split"
          }
          onClick={() => onSplit(speaker, selected.tier, selected.index, currentTime)}
        >
          Split at playhead
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!canMerge}
          title={canMerge ? "Merge with next segment on this tier" : "No next segment on this tier"}
          onClick={() => onMerge(speaker, selected.tier, selected.index)}
        >
          Merge with next
        </Button>
        <Button
          variant="danger"
          size="sm"
          onClick={() => onDelete(selected.tier, selected.index)}
        >
          Delete
        </Button>
      </div>
    </div>
  );
}
