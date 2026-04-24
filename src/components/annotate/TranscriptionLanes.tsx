import { useEffect, useMemo, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import { useAnnotationStore } from "../../stores/annotationStore";
import {
  useTranscriptionLanesStore,
  LANE_LABELS,
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
  /** Index into the underlying `record.tiers[kind].intervals` array. Set when
   * the strip is sourced from the editable tier (so inline edits / merges /
   * splits can address the original interval). Unset for legacy STT data
   * coming from the API cache. */
  sourceIndices?: number[];
  status?: "idle" | "loading" | "loaded" | "error";
}

// Lane order is hard-coded top-to-bottom and intentionally independent of
// each tier's numeric display_order (which only governs Praat export sort).
// Per the 4-lane viewer spec: phone IPA → word IPA → STT → ORTH.
const LANE_ORDER: LaneKind[] = ["ipa_phone", "ipa", "stt", "ortho"];

const LANE_HEIGHT_PX = 28;
export const LABEL_COL_PX = 56;
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
 * Four lanes — Phones / IPA / STT / ORTH — scroll horizontally in lock-step
 * with the waveform. Intervals keep their native Praat/ELAN boundaries.
 *
 * Editing affordances:
 *   • single-click an interval → seek to its start + select it (selection
 *     drives the segment-controls toolbar in AnnotationPanel)
 *   • double-click → inline contenteditable; Enter commits, Esc cancels
 *   • right-click → context menu with Edit / Split / Merge with next / Delete
 *
 * Only intervals overlapping the visible viewport (plus a small buffer) are
 * rendered, so a 5000-segment lane stays cheap.
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
  const selectedInterval = useTranscriptionLanesStore((s) => s.selectedInterval);
  const setSelectedInterval = useTranscriptionLanesStore((s) => s.setSelectedInterval);
  const record = useAnnotationStore((s) =>
    speaker ? s.records[speaker] ?? null : null,
  );
  const updateInterval = useAnnotationStore((s) => s.updateInterval);
  const removeInterval = useAnnotationStore((s) => s.removeInterval);
  const mergeIntervals = useAnnotationStore((s) => s.mergeIntervals);
  const splitInterval = useAnnotationStore((s) => s.splitInterval);

  const [pxPerSec, setPxPerSec] = useState(0);
  const [duration, setDuration] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [editing, setEditing] = useState<{ kind: LaneKind; index: number } | null>(null);
  const [menu, setMenu] = useState<
    { kind: LaneKind; index: number; x: number; y: number } | null
  >(null);
  const editRef = useRef<HTMLSpanElement | null>(null);

  const laneScrollRefs = useRef<Record<LaneKind, HTMLDivElement | null>>({
    ipa_phone: null,
    ipa: null,
    stt: null,
    ortho: null,
  });

  useEffect(() => {
    if (speaker) void ensureStt(speaker);
  }, [speaker, ensureStt]);

  // Close context menu / cancel inline edit when the user clicks elsewhere
  // or presses Escape. Caught at the document level so a misclick anywhere
  // dismisses the menu cleanly.
  useEffect(() => {
    if (!menu && !editing) return;
    const onDocDown = () => {
      setMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenu(null);
        setEditing(null);
      }
    };
    document.addEventListener("mousedown", onDocDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu, editing]);

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
        // Use the wrapper's parent (the visible viewport) for the rendered width,
        // not the wrapper itself which expands to the full timeline pixel width.
        setViewportWidth(wrapper.parentElement?.clientWidth ?? wrapper.clientWidth ?? 0);
      }
    };

    try {
      wrapper = ws.getWrapper();
    } catch {
      /* ignore */
    }
    readState();

    // WaveSurfer 7 emits scroll as (visibleStartSec, visibleEndSec, scrollLeftPx, scrollRightPx).
    // Read argument index 2 (pixel offset) — not index 0 which is start time in seconds.
    const onScroll = (_startSec: number, _endSec: number, leftPx: number) => {
      setScrollLeft(leftPx);
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

  // Keyboard shortcut: `s` splits the currently selected interval at the
  // WaveSurfer playhead. Suppressed while typing in any input/contenteditable
  // (including the inline lane editor) so it doesn't hijack keystrokes.
  useEffect(() => {
    const sel = selectedInterval;
    if (!sel || sel.speaker !== speaker) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "s" && e.key !== "S") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        if (target.isContentEditable) return;
      }
      const ws = wsRef.current;
      const t = ws?.getCurrentTime() ?? 0;
      e.preventDefault();
      splitInterval(sel.speaker, sel.tier, sel.index, t);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedInterval, speaker, splitInterval, wsRef]);

  // Focus + select-all when entering inline edit mode.
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
  }, [editing]);

  const strips: LaneStrip[] = useMemo(() => {
    const out: LaneStrip[] = [];
    for (const kind of LANE_ORDER) {
      if (!lanes[kind].visible) continue;

      // STT migration: if record.tiers.stt has entries, that is the editable
      // source of truth. Otherwise fall back to the API-cached sttBySpeaker
      // for legacy records that haven't been touched since the new tier
      // landed. Edits create the tier entry and from then on it wins.
      if (kind === "stt") {
        const tierIvs: AnnotationInterval[] = record?.tiers?.stt?.intervals ?? [];
        const hasTierStt = tierIvs.length > 0;
        if (hasTierStt) {
          const filtered: typeof tierIvs = [];
          const sourceIndices: number[] = [];
          tierIvs.forEach((iv, i) => {
            if (iv.text && iv.text.trim().length > 0) {
              filtered.push(iv);
              sourceIndices.push(i);
            }
          });
          out.push({
            kind: "stt",
            label: LANE_LABELS.stt,
            intervals: filtered,
            sourceIndices,
          });
        } else {
          const segs: SttSegment[] = sttBySpeaker[speaker] ?? [];
          out.push({
            kind: "stt",
            label: LANE_LABELS.stt,
            intervals: segs.map((s) => ({ start: s.start, end: s.end, text: s.text })),
            status: sttStatus[speaker] ?? "idle",
          });
        }
        continue;
      }

      const ivs: AnnotationInterval[] = record?.tiers?.[kind]?.intervals ?? [];
      const filtered: typeof ivs = [];
      const sourceIndices: number[] = [];
      ivs.forEach((iv, i) => {
        if (iv.text && iv.text.trim().length > 0) {
          filtered.push(iv);
          sourceIndices.push(i);
        }
      });
      out.push({
        kind,
        label: LANE_LABELS[kind],
        intervals: filtered,
        sourceIndices,
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

  const commitEdit = (kind: LaneKind, sourceIdx: number, text: string) => {
    const trimmed = text.trim();
    if (!speaker) return;
    updateInterval(speaker, kind, sourceIdx, trimmed);
    setEditing(null);
  };

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
        let visibleSourceIndices: number[] | undefined = strip.sourceIndices;
        let firstIdx = 0;
        if (!isEmpty && strip.intervals.length > 200) {
          firstIdx = firstOverlappingIdx(strip.intervals, visibleStartSec);
          let lastIdx = firstIdx;
          while (
            lastIdx < strip.intervals.length &&
            strip.intervals[lastIdx].start <= visibleEndSec
          ) {
            lastIdx += 1;
          }
          visible = strip.intervals.slice(firstIdx, lastIdx);
          if (strip.sourceIndices) {
            visibleSourceIndices = strip.sourceIndices.slice(firstIdx, lastIdx);
          }
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
                  {visible.map((iv, slotIdx) => {
                    const sourceIdx = visibleSourceIndices?.[slotIdx];
                    const left = iv.start * pxPerSec;
                    const width = Math.max(1, (iv.end - iv.start) * pxPerSec);
                    const showLabel = width >= MIN_LABEL_WIDTH_PX;
                    const isEditable = sourceIdx !== undefined;
                    const isSelected =
                      isEditable &&
                      selectedInterval?.speaker === speaker &&
                      selectedInterval?.tier === strip.kind &&
                      selectedInterval?.index === sourceIdx;
                    const isEditing =
                      isEditable &&
                      editing?.kind === strip.kind &&
                      editing?.index === sourceIdx;

                    const baseStyle: React.CSSProperties = {
                      left,
                      width,
                      backgroundColor: withAlpha(color, isSelected ? 0.28 : 0.14),
                      borderLeft: `2px solid ${color}`,
                      color: "#334155",
                      ...({ ["--tw-ring-color"]: color } as React.CSSProperties),
                    };

                    if (isEditing && sourceIdx !== undefined) {
                      return (
                        <span
                          key={`${strip.kind}-edit-${sourceIdx}`}
                          ref={editRef}
                          contentEditable
                          suppressContentEditableWarning
                          onMouseDown={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              commitEdit(
                                strip.kind,
                                sourceIdx,
                                e.currentTarget.textContent ?? "",
                              );
                            } else if (e.key === "Escape") {
                              e.preventDefault();
                              setEditing(null);
                            }
                          }}
                          onBlur={(e) =>
                            commitEdit(
                              strip.kind,
                              sourceIdx,
                              e.currentTarget.textContent ?? "",
                            )
                          }
                          className="absolute top-1 bottom-1 flex items-center overflow-hidden rounded px-1 text-[10px] font-medium outline-none ring-2"
                          style={baseStyle}
                          aria-label={`Edit ${strip.label} text`}
                        >
                          {iv.text}
                        </span>
                      );
                    }

                    return (
                      <button
                        key={`${strip.kind}-${slotIdx}-${iv.start}`}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isEditable && sourceIdx !== undefined) {
                            setSelectedInterval({
                              speaker,
                              tier: strip.kind,
                              index: sourceIdx,
                            });
                          }
                          onSeek?.(iv.start);
                        }}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          if (isEditable && sourceIdx !== undefined) {
                            setEditing({ kind: strip.kind, index: sourceIdx });
                          }
                        }}
                        onContextMenu={(e) => {
                          if (!isEditable || sourceIdx === undefined) return;
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedInterval({
                            speaker,
                            tier: strip.kind,
                            index: sourceIdx,
                          });
                          setMenu({
                            kind: strip.kind,
                            index: sourceIdx,
                            x: e.clientX,
                            y: e.clientY,
                          });
                        }}
                        className={
                          "absolute top-1 bottom-1 flex items-center overflow-hidden rounded px-1 text-[10px] font-medium transition hover:ring-1" +
                          (isSelected ? " ring-2" : "")
                        }
                        style={baseStyle}
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

      {menu && (() => {
        const target = record?.tiers?.[menu.kind]?.intervals?.[menu.index];
        if (!target) return null;
        return (
          <ContextMenu
            x={menu.x}
            y={menu.y}
            laneLabel={LANE_LABELS[menu.kind]}
            start={target.start}
            end={target.end}
            onEdit={() => {
              setEditing({ kind: menu.kind, index: menu.index });
              setMenu(null);
            }}
            onSplit={() => {
              const ws = wsRef.current;
              const t = ws?.getCurrentTime() ?? 0;
              splitInterval(speaker, menu.kind, menu.index, t);
              setMenu(null);
            }}
            onMerge={() => {
              mergeIntervals(speaker, menu.kind, menu.index);
              setMenu(null);
            }}
            onDelete={() => {
              removeInterval(speaker, menu.kind, menu.index);
              setSelectedInterval(null);
              setMenu(null);
            }}
          />
        );
      })()}
    </div>
  );
}

interface ContextMenuProps {
  x: number;
  y: number;
  laneLabel: string;
  start: number;
  end: number;
  onEdit: () => void;
  onSplit: () => void;
  onMerge: () => void;
  onDelete: () => void;
}

function ContextMenu({
  x,
  y,
  laneLabel,
  start,
  end,
  onEdit,
  onSplit,
  onMerge,
  onDelete,
}: ContextMenuProps) {
  return (
    <div
      onMouseDown={(e) => e.stopPropagation()}
      className="fixed z-50 min-w-[200px] rounded border border-slate-200 bg-white py-1 text-[12px] shadow-lg"
      style={{ left: x, top: y }}
      role="menu"
    >
      <div className="px-3 pt-1 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        {laneLabel}
        <span className="ml-2 font-mono text-[10px] font-normal normal-case tracking-normal text-slate-400">
          {start.toFixed(3)}–{end.toFixed(3)}s
        </span>
      </div>
      <div className="mb-1 h-px bg-slate-100" />
      <MenuItem label="Edit text" hint="dbl-click" onClick={onEdit} />
      <MenuItem label="Split at playhead" hint="S" onClick={onSplit} />
      <MenuItem label="Merge with next" onClick={onMerge} />
      <div className="my-1 h-px bg-slate-100" />
      <MenuItem label="Delete" danger onClick={onDelete} />
    </div>
  );
}

function MenuItem({
  label,
  hint,
  danger,
  onClick,
}: {
  label: string;
  hint?: string;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={
        "flex w-full items-center justify-between px-3 py-1 text-left hover:bg-slate-50" +
        (danger ? " text-red-600" : " text-slate-700")
      }
    >
      <span>{label}</span>
      {hint ? <span className="ml-4 text-[10px] text-slate-400">{hint}</span> : null}
    </button>
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
