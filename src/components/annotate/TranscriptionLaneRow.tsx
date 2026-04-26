import type React from "react";
import type { LaneKind } from "../../stores/transcriptionLanesStore";

export interface LaneInterval {
  start: number;
  end: number;
  text: string;
  manuallyAdjusted?: boolean;
}

export interface LaneStrip {
  kind: LaneKind;
  label: string;
  intervals: LaneInterval[];
  tier?: string;
  sourceIndices?: number[];
  intervalColors?: (string | undefined)[];
  boundaryOnly?: boolean;
  needsMigration?: boolean;
  migrate?: () => void;
  status?: "idle" | "loading" | "loaded" | "error";
  emptyHint?: string;
}

const LANE_HEIGHT_PX = 28;
const MIN_LABEL_WIDTH_PX = 18;

export function TranscriptionLaneRow({
  color,
  editing,
  emptyMsg = "",
  firstIdx,
  innerWidth,
  isEmpty,
  pendingDrag,
  pxPerSec,
  selectedInterval,
  showEmptyHint,
  speaker,
  strip,
  visible,
  visibleSourceIndices,
  onBeginDrag,
  onCommitEdit,
  onContextMenu,
  onDoubleClickInterval,
  onSeekInterval,
  setEditRef,
  setEditing,
  setLaneScrollRef,
}: {
  color: string;
  editing: { kind: LaneKind; index: number } | null;
  emptyMsg?: string;
  firstIdx: number;
  innerWidth: number;
  isEmpty: boolean;
  pendingDrag: { kind: LaneKind; tier: string; startSec: number; endSec: number } | null;
  pxPerSec: number;
  selectedInterval: { speaker: string; tier: string; index: number } | null;
  showEmptyHint: boolean;
  speaker: string;
  strip: LaneStrip;
  visible: LaneInterval[];
  visibleSourceIndices?: number[];
  onBeginDrag: (strip: LaneStrip, event: React.MouseEvent<HTMLDivElement>) => void;
  onCommitEdit: (tier: string, sourceIdx: number, text: string) => void;
  onContextMenu: (
    strip: LaneStrip,
    sourceIdx: number,
    event: React.MouseEvent<HTMLButtonElement>,
  ) => void;
  onDoubleClickInterval: (strip: LaneStrip, sourceIdx: number) => void;
  onSeekInterval: (iv: LaneInterval, sourceIdx: number | undefined, tierName: string) => void;
  setEditRef: (element: HTMLSpanElement | null) => void;
  setEditing: (editing: { kind: LaneKind; index: number } | null) => void;
  setLaneScrollRef: (kind: LaneKind, element: HTMLDivElement | null) => void;
}) {
  return (
    <div className="relative flex items-stretch">
      <div
        className="flex shrink-0 items-center justify-center border-r border-slate-100 text-[9px] font-semibold uppercase tracking-wider"
        style={{ width: 56, color }}
        title={`${strip.label} lane`}
      >
        {strip.label}
      </div>
      <div className="relative flex-1 overflow-hidden" style={{ height: LANE_HEIGHT_PX }}>
        <div
          ref={(el) => {
            setLaneScrollRef(strip.kind, el);
          }}
          className="h-full overflow-hidden"
        >
          <div
            className="relative h-full"
            style={{ width: innerWidth }}
            onMouseDown={(e) => {
              if (!strip.boundaryOnly) return;
              if (e.button !== 0) return;
              const target = e.target as HTMLElement | null;
              if (target?.closest("button")) return;
              onBeginDrag(strip, e);
            }}
          >
            {pendingDrag?.kind === strip.kind && (() => {
              const a = Math.min(pendingDrag.startSec, pendingDrag.endSec);
              const b = Math.max(pendingDrag.startSec, pendingDrag.endSec);
              return (
                <div
                  className="pointer-events-none absolute top-1 bottom-1 rounded border-2 border-dashed"
                  style={{
                    left: a * pxPerSec,
                    width: Math.max(1, (b - a) * pxPerSec),
                    borderColor: color,
                    backgroundColor: withAlpha(color, 0.12),
                  }}
                />
              );
            })()}
            {visible.map((iv, slotIdx) => {
              const sourceIdx = visibleSourceIndices?.[slotIdx];
              const absIdx = firstIdx + slotIdx;
              const left = iv.start * pxPerSec;
              const width = Math.max(1, (iv.end - iv.start) * pxPerSec);
              const showLabel = !strip.boundaryOnly && width >= MIN_LABEL_WIDTH_PX;
              const isEditable = sourceIdx !== undefined;
              const tierName = strip.tier ?? strip.kind;
              const isSelected =
                isEditable &&
                selectedInterval?.speaker === speaker &&
                selectedInterval?.tier === tierName &&
                selectedInterval?.index === sourceIdx;
              const isEditing =
                isEditable && editing?.kind === strip.kind && editing?.index === sourceIdx;
              const ivColor = strip.intervalColors?.[absIdx] ?? color;

              const baseStyle: React.CSSProperties = {
                left,
                width,
                backgroundColor: withAlpha(ivColor, isSelected ? 0.28 : 0.14),
                borderLeft: `2px solid ${ivColor}`,
                color: "#334155",
                ...({ ["--tw-ring-color"]: ivColor } as React.CSSProperties),
              };

              if (isEditing && sourceIdx !== undefined) {
                return (
                  <span
                    key={`${strip.kind}-edit-${sourceIdx}`}
                    ref={setEditRef}
                    contentEditable
                    suppressContentEditableWarning
                    onMouseDown={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        onCommitEdit(tierName, sourceIdx, e.currentTarget.textContent ?? "");
                      } else if (e.key === "Escape") {
                        e.preventDefault();
                        setEditing(null);
                      }
                    }}
                    onBlur={(e) => {
                      onCommitEdit(tierName, sourceIdx, e.currentTarget.textContent ?? "");
                    }}
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
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSeekInterval(iv, sourceIdx, tierName);
                  }}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    if (sourceIdx === undefined) return;
                    onDoubleClickInterval(strip, sourceIdx);
                  }}
                  onContextMenu={(e) => {
                    if (sourceIdx === undefined) return;
                    e.preventDefault();
                    e.stopPropagation();
                    onContextMenu(strip, sourceIdx, e);
                  }}
                  className={
                    "absolute top-1 bottom-1 flex items-center overflow-hidden rounded px-1 text-[10px] font-medium transition hover:ring-1" +
                    (isSelected ? " ring-2" : "")
                  }
                  style={baseStyle}
                  title={
                    strip.boundaryOnly
                      ? `${iv.start.toFixed(3)}–${iv.end.toFixed(3)} s${
                          iv.manuallyAdjusted ? " · manually adjusted" : ""
                        }`
                      : `${iv.start.toFixed(3)}–${iv.end.toFixed(3)} s · ${iv.text}`
                  }
                  aria-label={`${strip.label} ${iv.start.toFixed(2)}s${iv.text ? `: ${iv.text}` : ""}`}
                >
                  {showLabel ? <span className="truncate">{iv.text}</span> : null}
                  {iv.manuallyAdjusted && (
                    <span
                      aria-hidden
                      className="pointer-events-none absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: ivColor }}
                      title="Manually adjusted"
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>
        {showEmptyHint && isEmpty && (
          <div className="pointer-events-none absolute inset-0 flex items-center pl-2 text-[10px] italic text-slate-400">
            {emptyMsg}
          </div>
        )}
      </div>
    </div>
  );
}

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
