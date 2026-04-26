import { useEffect, useMemo, useState } from "react";

import { Button } from "../../shared/Button";
import { Input } from "../../shared/Input";
import {
  useTranscriptionLanesStore,
  labelForTier,
} from "../../../stores/transcriptionLanesStore";

import type { SegmentEditorProps } from "./types";

export function IntervalEditor({
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
}: SegmentEditorProps) {
  const setSelectedInterval = useTranscriptionLanesStore((s) => s.setSelectedInterval);
  return (
    <SegmentControls
      speaker={speaker}
      currentTime={currentTime}
      selected={selected}
      record={record}
      onUpdateText={onUpdateText}
      onUpdateTimes={onUpdateTimes}
      onMerge={onMerge}
      onSplit={onSplit}
      onDelete={(tier, index) => {
        onDelete(tier, index);
        setSelectedInterval(null);
      }}
      onClearSelection={() => {
        setSelectedInterval(null);
        onClearSelection();
      }}
    />
  );
}

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
}: SegmentEditorProps) {
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
            ({labelForTier(selected.tier)} #{selected.index + 1})
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
