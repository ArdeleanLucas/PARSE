import { useCallback, useEffect, useState } from "react";
import type React from "react";
import type { LaneKind } from "../../stores/transcriptionLanesStore";
import type { LaneStrip } from "./TranscriptionLaneRow";

export interface PendingBoundaryDrag {
  kind: LaneKind;
  tier: string;
  startSec: number;
  endSec: number;
}

export function useTranscriptionLaneBoundaryEdit({
  addInterval,
  duration,
  laneScrollRefs,
  pxPerSec,
  speaker,
  stripByKind,
}: {
  addInterval: (
    speaker: string,
    tier: string,
    interval: { start: number; end: number; text: string; manuallyAdjusted?: boolean },
  ) => void;
  duration: number;
  laneScrollRefs: React.RefObject<Record<LaneKind, HTMLDivElement | null>>;
  pxPerSec: number;
  speaker: string;
  stripByKind: (kind: LaneKind) => LaneStrip | undefined;
}) {
  const [pendingDrag, setPendingDrag] = useState<PendingBoundaryDrag | null>(null);

  useEffect(() => {
    if (!pendingDrag) return;
    if (!speaker || pxPerSec <= 0) return;

    const onMove = (e: MouseEvent) => {
      const laneEl = laneScrollRefs.current?.[pendingDrag.kind];
      if (!laneEl) return;
      const rect = laneEl.getBoundingClientRect();
      const px = e.clientX - rect.left + laneEl.scrollLeft;
      const sec = Math.max(0, Math.min(duration, px / pxPerSec));
      setPendingDrag((prev) => (prev ? { ...prev, endSec: sec } : prev));
    };

    const onUp = () => {
      setPendingDrag((prev) => {
        if (!prev) return null;
        const a = Math.min(prev.startSec, prev.endSec);
        const b = Math.max(prev.startSec, prev.endSec);
        if (b - a >= 0.05) {
          const strip = stripByKind(prev.kind);
          if (strip?.needsMigration) strip.migrate?.();
          addInterval(speaker, prev.tier, {
            start: a,
            end: b,
            text: "",
            manuallyAdjusted: true,
          });
        }
        return null;
      });
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [addInterval, duration, laneScrollRefs, pendingDrag, pxPerSec, speaker, stripByKind]);

  const beginDrag = useCallback(
    (strip: LaneStrip, event: React.MouseEvent<HTMLDivElement>) => {
      if (!speaker || pxPerSec <= 0) return;
      const tier = strip.tier ?? strip.kind;
      const sec = Math.max(
        0,
        Math.min(duration, (event.nativeEvent as MouseEvent).offsetX / pxPerSec),
      );
      setPendingDrag({
        kind: strip.kind,
        tier,
        startSec: sec,
        endSec: sec,
      });
      event.preventDefault();
    },
    [duration, pxPerSec, speaker],
  );

  return { beginDrag, pendingDrag };
}
