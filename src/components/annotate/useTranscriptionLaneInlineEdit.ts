import { useCallback, useEffect, useState } from "react";
import type React from "react";
import type { LaneKind } from "../../stores/transcriptionLanesStore";
import type { LaneStrip } from "./TranscriptionLaneRow";

export function useTranscriptionLaneInlineEdit({
  editRef,
  speaker,
  updateInterval,
}: {
  editRef: React.RefObject<HTMLSpanElement | null>;
  speaker: string;
  updateInterval: (speaker: string, tier: string, sourceIdx: number, text: string) => void;
}) {
  const [editing, setEditing] = useState<{ kind: LaneKind; index: number } | null>(null);

  useEffect(() => {
    if (!editing) return;
    const el = editRef.current;
    if (!el) return;
    el.focus();
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
  }, [editRef, editing]);

  const commitEdit = useCallback(
    (tier: string, sourceIdx: number, text: string) => {
      const trimmed = text.trim();
      if (!speaker) return;
      updateInterval(speaker, tier, sourceIdx, trimmed);
      setEditing(null);
    },
    [speaker, updateInterval],
  );

  const beginIntervalEdit = useCallback((strip: LaneStrip, sourceIdx: number) => {
    if (strip.boundaryOnly) return;
    if (strip.needsMigration) strip.migrate?.();
    setEditing({ kind: strip.kind, index: sourceIdx });
  }, []);

  return { beginIntervalEdit, commitEdit, editing, setEditing };
}
