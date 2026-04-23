import { useEffect, useMemo, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import { useAnnotationStore } from "../../stores/annotationStore";
import {
  useTranscriptionLanesStore,
  type LaneKind,
} from "../../stores/transcriptionLanesStore";
import type { AnnotationInterval, SttSegment } from "../../api/types";

interface TranscriptionLanesProps {
  speaker: string;
  wsRef: React.RefObject<WaveSurfer | null>;
  audioReady: boolean;
  onSeek?: (timeSec: number) => void;
}

interface LaneStrip {
  kind: LaneKind;
  label: string;
  intervals: Array<{ start: number; end: number; text: string }>;
  status?: "idle" | "loading" | "loaded" | "error";
}

const LANE_LABELS: Record<LaneKind, string> = {
  stt: "STT",
  ipa: "IPA",
  ortho: "ORTHO",
};

const LANE_HEIGHT_PX = 28;
export const LABEL_COL_PX = 48;
const MIN_LABEL_WIDTH_PX = 18;
const VIRTUAL_BUFFER_PX = 400;

function firstOverlappingIdx(
  sorted: Array<{ start: number; end: number }>,
  timeSec: number,
): number {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sorted[mid].end < timeSec) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * Stacked transcription lanes rendered below the WaveSurfer waveform.
 *
 * Each visible lane scrolls horizontally in lock-step with the waveform so
 * labelled intervals stay aligned with their audio. Intervals keep their
 * native Praat/ELAN boundaries (no re-bucketing). Only intervals overlapping
 * the visible viewport (plus a small buffer) are rendered, so a 5000-segment
 * lane stays cheap.
 */
export function TranscriptionLanes({
  speaker,
  wsRef,
  audioReady,
  onSeek,
}: TranscriptionLanesProps) {
  const lanes = useTranscriptionLanesStore((s) => s.lanes);
  const sttBySpeaker = useTranscriptionLanesStore((s) => s.sttBySpeaker);
  const sttStatus = useTranscriptionLanesStore((s) => s.sttStatus);
  const ensureStt = useTranscriptionLanesStore((s) => s.ensureStt);
  const record = useAnnotationStore((s) =>
    speaker ? s.records[speaker] ?? null : null,
  );

  const [pxPerSec, setPxPerSec] = useState(0);
  const [duration, setDuration] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(0);
  const laneScrollRefs = useRef<Record<LaneKind, HTMLDivElement | null>>({
    stt: null,
    ipa: null,
    ortho: null,
  });

  useEffect(() => {
    if (speaker) void ensureStt(speaker);
  }, [speaker, ensureStt]);

  useEffect(() => {
    if (!audioReady) return;
    const ws = wsRef.current;
    if (!ws) return;

    let wrapper: HTMLElement | null = null;

    const readState = () => {
      const opts = (ws as unknown as { options: { minPxPerSec?: number } }).options;
      setPxPerSec(opts?.minPxPerSec ?? 0);
      setDuration(ws.getDuration() ?? 0);
      if (wrapper) {
        setScrollLeft(wrapper.scrollLeft ?? 0);
        setViewportWidth(wrapper.clientWidth ?? 0);
      }
    };

    try {
      wrapper = ws.getWrapper();
    } catch {
      /* ignore */
    }
    readState();

    const onScroll = (left: number) => {
      setScrollLeft(left);
    };
    const onZoom = () => readState();
    const onReady = () => readState();

    ws.on("scroll", onScroll);
    ws.on("zoom", onZoom);
    ws.on("ready", onReady);

    const resizeObs =
      wrapper && typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => readState())
        : null;
    if (wrapper && resizeObs) resizeObs.observe(wrapper);

    return () => {
      ws.un("scroll", onScroll);
      ws.un("zoom", onZoom);
      ws.un("ready", onReady);
      resizeObs?.disconnect();
    };
  }, [audioReady, wsRef, speaker]);

  useEffect(() => {
    for (const kind of Object.keys(laneScrollRefs.current) as LaneKind[]) {
      const el = laneScrollRefs.current[kind];
      if (el && Math.abs(el.scrollLeft - scrollLeft) > 0.5) {
        el.scrollLeft = scrollLeft;
      }
    }
  }, [scrollLeft]);

  const strips: LaneStrip[] = useMemo(() => {
    const out: LaneStrip[] = [];
    if (lanes.stt.visible) {
      const segs: SttSegment[] = sttBySpeaker[speaker] ?? [];
      out.push({
        kind: "stt",
        label: LANE_LABELS.stt,
        intervals: segs.map((s) => ({
          start: s.start,
          end: s.end,
          text: s.text,
        })),
        status: sttStatus[speaker] ?? "idle",
      });
    }
    if (lanes.ipa.visible) {
      const ivs: AnnotationInterval[] = record?.tiers?.ipa?.intervals ?? [];
      out.push({
        kind: "ipa",
        label: LANE_LABELS.ipa,
        intervals: ivs.filter((i) => i.text && i.text.trim().length > 0),
      });
    }
    if (lanes.ortho.visible) {
      const ivs: AnnotationInterval[] = record?.tiers?.ortho?.intervals ?? [];
      out.push({
        kind: "ortho",
        label: LANE_LABELS.ortho,
        intervals: ivs.filter((i) => i.text && i.text.trim().length > 0),
      });
    }
    return out;
  }, [lanes, sttBySpeaker, sttStatus, record, speaker]);

  if (strips.length === 0 || !audioReady || pxPerSec <= 0 || duration <= 0) {
    return null;
  }

  const innerWidth = Math.max(viewportWidth, pxPerSec * duration);
  const visibleStartSec = Math.max(0, (scrollLeft - VIRTUAL_BUFFER_PX) / pxPerSec);
  const visibleEndSec =
    (scrollLeft + viewportWidth + VIRTUAL_BUFFER_PX) / pxPerSec;

  return (
    <div className="mt-2 space-y-1 px-5">
      {strips.map((strip) => {
        const color = lanes[strip.kind].color;
        const isEmpty = strip.intervals.length === 0;
        let emptyMsg = "";
        if (isEmpty) {
          if (strip.kind === "stt") {
            emptyMsg =
              strip.status === "loading"
                ? "Loading STT…"
                : strip.status === "error"
                  ? "Failed to load STT"
                  : `No STT cache — run Orthographic STT for ${speaker}`;
          } else {
            emptyMsg = `No ${strip.label} intervals yet`;
          }
        }

        // Virtualized slice: only render intervals that overlap the viewport
        // (plus buffer). Intervals are sorted by start ascending.
        let visible: LaneStrip["intervals"] = strip.intervals;
        if (!isEmpty && strip.intervals.length > 200) {
          const firstIdx = firstOverlappingIdx(strip.intervals, visibleStartSec);
          let lastIdx = firstIdx;
          while (
            lastIdx < strip.intervals.length &&
            strip.intervals[lastIdx].start <= visibleEndSec
          ) {
            lastIdx += 1;
          }
          visible = strip.intervals.slice(firstIdx, lastIdx);
        }

        return (
          <div key={strip.kind} className="relative flex items-stretch">
            <div
              className="flex shrink-0 items-center justify-center border-r border-slate-100 text-[9px] font-semibold uppercase tracking-wider"
              style={{ width: LABEL_COL_PX, color }}
              title={`${strip.label} lane`}
            >
              {strip.label}
            </div>
            <div className="relative flex-1 overflow-hidden" style={{ height: LANE_HEIGHT_PX }}>
              <div
                ref={(el) => {
                  laneScrollRefs.current[strip.kind] = el;
                }}
                className="h-full overflow-hidden"
              >
                <div className="relative h-full" style={{ width: innerWidth }}>
                  {visible.map((iv, idx) => {
                    const left = iv.start * pxPerSec;
                    const width = Math.max(1, (iv.end - iv.start) * pxPerSec);
                    const showLabel = width >= MIN_LABEL_WIDTH_PX;
                    return (
                      <button
                        key={`${strip.kind}-${idx}-${iv.start}`}
                        type="button"
                        onClick={() => onSeek?.(iv.start)}
                        className="absolute top-1 bottom-1 flex items-center overflow-hidden rounded px-1 text-[10px] font-medium transition hover:ring-1"
                        style={{
                          left,
                          width,
                          backgroundColor: withAlpha(color, 0.14),
                          borderLeft: `2px solid ${color}`,
                          color: "#334155",
                          ...({ ["--tw-ring-color"]: color } as React.CSSProperties),
                        }}
                        title={`${iv.start.toFixed(3)}–${iv.end.toFixed(3)} s · ${iv.text}`}
                        aria-label={`${strip.label} ${iv.start.toFixed(2)}s: ${iv.text}`}
                      >
                        {showLabel ? <span className="truncate">{iv.text}</span> : null}
                      </button>
                    );
                  })}
                </div>
              </div>
              {isEmpty && (
                <div className="pointer-events-none absolute inset-0 flex items-center pl-2 text-[10px] italic text-slate-400">
                  {emptyMsg}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Mix hex `#rrggbb` with a white background at the given alpha. Produces a
 * pastel fill that stays visible on a white background even for bright source
 * colors (unlike `#rrggbb + "22"` alpha stacking, which vanishes on yellows).
 */
function withAlpha(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  const a = Math.max(0, Math.min(1, alpha));
  const mix = (c: number) => Math.round(c * a + 255 * (1 - a));
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}
