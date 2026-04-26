import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  intervals: Array<{
    start: number;
    end: number;
    text: string;
    manuallyAdjusted?: boolean;
  }>;
  /** Annotation tier name to dispatch store actions against. When unset
   * (legacy code path), the lane `kind` is used. The two diverge for the
   * Words and BND lanes: `kind: "stt_words"` → `tier: "stt_words"`,
   * `kind: "boundaries"` → `tier: "ortho_words"`. */
  tier?: string;
  /** Index into the underlying `record.tiers[tier].intervals` array. Set when
   * the strip is sourced from the editable tier (so inline edits / merges /
   * splits can address the original interval). */
  sourceIndices?: number[];
  /** Per-interval color override aligned to `intervals[]`. Used by the
   * Boundaries lane to color each Tier 2 word by its shift from the matching
   * Tier 1 word (or by Tier 2 confidence when no Tier 1 partner exists).
   * When unset, the lane's single color from the store is used. */
  intervalColors?: (string | undefined)[];
  /** Boundary-only lanes (Words, BND) suppress text labels inside boxes.
   * Text content lives in STT/ORTH/IPA — these lanes are pure timing. */
  boundaryOnly?: boolean;
  /** True when the editable tier hasn't been populated yet for this lane.
   * Edit-path handlers must call the corresponding `ensure*Tier` migration
   * before opening the editor / committing edits so the tier entry exists. */
  needsMigration?: boolean;
  /** Migration callback to run on first edit; resolves `needsMigration`. */
  migrate?: () => void;
  status?: "idle" | "loading" | "loaded" | "error";
  /** Custom empty-state message; falls back to a generic per-tier hint. */
  emptyHint?: string;
}

// Lane order is hard-coded top-to-bottom and intentionally independent of
// each tier's numeric display_order (which only governs Praat export sort).
// Phone IPA → word IPA → STT → ORTH → Words (Tier 1) → Boundaries (Tier 2).
// Words sits directly above Boundaries so a researcher reading the strips
// top-down sees the same word at both Tier 1 and Tier 2 positions and can
// eyeball the shift without color-coding alone.
const LANE_ORDER: LaneKind[] = ["ipa_phone", "ipa", "stt", "ortho", "stt_words", "boundaries"];

/** Tier 2 forced-align ±pad window; matches forced_align.py:_slice_window
 * default. A Tier 1 word boundary off by more than this frequently means the
 * CTC slice cut the phoneme — the case the Boundaries lane flags red. */
const BOUNDARY_PAD_MS = 100;
const BOUNDARY_GREEN_MS = 50;

const BND_COLOR_GREEN = "#059669";
const BND_COLOR_AMBER = "#d97706";
const BND_COLOR_RED = "#dc2626";
const BND_COLOR_UNKNOWN = "#64748b";

function boundaryColor(
  tier2: { start: number; end: number; confidence?: number; source?: string },
  tier1: { start: number; end: number } | undefined,
): string {
  if (tier2.source === "short_clip_fallback") return BND_COLOR_RED;
  if (
    tier1 &&
    Number.isFinite(tier1.start) &&
    Number.isFinite(tier1.end) &&
    !(tier1.start === 0 && tier1.end === 0)
  ) {
    const onMs = Math.abs(tier2.start - tier1.start) * 1000;
    const offMs = Math.abs(tier2.end - tier1.end) * 1000;
    const edgeMs = Math.max(onMs, offMs);
    if (edgeMs > BOUNDARY_PAD_MS) return BND_COLOR_RED;
    if (edgeMs >= BOUNDARY_GREEN_MS) return BND_COLOR_AMBER;
    return BND_COLOR_GREEN;
  }
  const conf = tier2.confidence;
  if (typeof conf !== "number") return BND_COLOR_UNKNOWN;
  if (conf < 0.4) return BND_COLOR_RED;
  if (conf < 0.7) return BND_COLOR_AMBER;
  return BND_COLOR_GREEN;
}

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
  const addInterval = useAnnotationStore((s) => s.addInterval);
  const ensureSttTier = useAnnotationStore((s) => s.ensureSttTier);
  const ensureSttWordsTier = useAnnotationStore((s) => s.ensureSttWordsTier);

  const [pxPerSec, setPxPerSec] = useState(0);
  const [duration, setDuration] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [editing, setEditing] = useState<{ kind: LaneKind; index: number } | null>(null);
  const [menu, setMenu] = useState<
    { kind: LaneKind; index: number; x: number; y: number } | null
  >(null);
  /** Active drag-to-create-interval on a boundary-only lane. The user
   * presses on an empty region of the lane and drags rightward; on
   * release we commit a new ``manuallyAdjusted`` interval to that lane's
   * tier. ``startX`` and ``currentX`` are pixels relative to the timeline
   * inner div (already includes scroll offset). */
  const [pendingDrag, setPendingDrag] = useState<
    | { kind: LaneKind; tier: string; startSec: number; endSec: number }
    | null
  >(null);
  const editRef = useRef<HTMLSpanElement | null>(null);

  const laneScrollRefs = useRef<Record<LaneKind, HTMLDivElement | null>>({
    ipa_phone: null,
    ipa: null,
    stt: null,
    ortho: null,
    stt_words: null,
    boundaries: null,
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
      // ``sel.tier`` is the annotation tier name (mapped at selection time).
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

      if (kind === "stt_words") {
        // Words is a boundary-only lane (no text inside boxes). The text
        // for each word belongs in STT/ORTH segment-level tiers; Words
        // exists purely so the user can see and adjust where Tier 1
        // placed word boundaries (and add new ones in gaps where the
        // model produced nothing).
        //
        // Source priority: ``record.tiers.stt_words`` post-migration,
        // else fall back to the API-cached ``segments[].words[]``.
        // ``ensureSttWordsTier`` flips us to the migrated path on first
        // edit (drag, split, merge, delete, add-in-gap).
        const tierIvs: AnnotationInterval[] =
          record?.tiers?.stt_words?.intervals ?? [];
        const hasTier = tierIvs.length > 0;
        if (hasTier) {
          out.push({
            kind: "stt_words",
            tier: "stt_words",
            label: LANE_LABELS.stt_words,
            intervals: tierIvs.map((iv) => ({
              start: iv.start,
              end: iv.end,
              text: "",
              manuallyAdjusted: iv.manuallyAdjusted,
            })),
            sourceIndices: tierIvs.map((_, i) => i),
            boundaryOnly: true,
          });
        } else {
          const segs: SttSegment[] = sttBySpeaker[speaker] ?? [];
          const intervals: LaneStrip["intervals"] = [];
          for (const seg of segs) {
            for (const w of seg.words ?? []) {
              if (w.start === 0 && w.end === 0) continue;
              intervals.push({ start: w.start, end: w.end, text: "" });
            }
          }
          const status = sttStatus[speaker] ?? "idle";
          const emptyHint =
            intervals.length > 0
              ? undefined
              : status === "loading"
                ? "Loading STT…"
                : status === "error"
                  ? "Failed to load STT"
                  : `No word-level STT yet — run word-level STT for ${speaker}`;
          out.push({
            kind: "stt_words",
            tier: "stt_words",
            label: LANE_LABELS.stt_words,
            intervals,
            sourceIndices: intervals.map((_, i) => i),
            boundaryOnly: true,
            needsMigration: true,
            migrate: () => ensureSttWordsTier(speaker, segs),
            emptyHint,
            status,
          });
        }
        continue;
      }

      if (kind === "boundaries") {
        // BND is a boundary-only lane (no text inside boxes). It edits
        // ``tiers.ortho_words`` directly — the persisted refined word
        // boundaries from Tier 2 forced alignment. Color-coded by shift
        // to the matching Tier 1 word; falls back to Tier 2 confidence
        // when no Tier 1 partner exists.
        const segs: SttSegment[] = sttBySpeaker[speaker] ?? [];
        const tier1Words: Array<{ start: number; end: number; text: string }> = [];
        for (const seg of segs) {
          for (const w of seg.words ?? []) {
            tier1Words.push({ start: w.start, end: w.end, text: w.word });
          }
        }
        const tier2Ivs = (record?.tiers?.ortho_words?.intervals ?? []) as Array<{
          start: number;
          end: number;
          text: string;
          confidence?: number;
          source?: "forced_align" | "short_clip_fallback";
          manuallyAdjusted?: boolean;
        }>;

        const intervals: LaneStrip["intervals"] = [];
        const intervalColors: (string | undefined)[] = [];
        const sourceIndices: number[] = [];
        tier2Ivs.forEach((iv, i) => {
          intervals.push({
            start: iv.start,
            end: iv.end,
            text: "",
            manuallyAdjusted: iv.manuallyAdjusted,
          });
          intervalColors.push(boundaryColor(iv, tier1Words[i]));
          sourceIndices.push(i);
        });

        const hasTier2 = intervals.length > 0;
        const emptyHint = hasTier2
          ? undefined
          : tier1Words.length > 0
            ? "Run forced-align (or drag here to add a boundary manually)"
            : `Run Orthographic STT for ${speaker}, then forced-align`;

        out.push({
          kind: "boundaries",
          tier: "ortho_words",
          label: LANE_LABELS.boundaries,
          intervals,
          intervalColors,
          sourceIndices,
          boundaryOnly: true,
          emptyHint,
        });
        continue;
      }

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
          // Pre-migration: STT sourced from the API cache. Emit identity
          // sourceIndices so the strip is treated as editable in handlers;
          // `needsMigration` flips the double-click / right-click paths to
          // run `ensureSttTier` before opening the editor. Single-click seek
          // stays untouched — no migration until the user actually edits.
          const segs: SttSegment[] = sttBySpeaker[speaker] ?? [];
          out.push({
            kind: "stt",
            tier: "stt",
            label: LANE_LABELS.stt,
            intervals: segs.map((s) => ({ start: s.start, end: s.end, text: s.text })),
            sourceIndices: segs.map((_, i) => i),
            needsMigration: true,
            migrate: () => ensureSttTier(speaker, segs),
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

  const stripByKind = useCallback(
    (kind: LaneKind): LaneStrip | undefined => strips.find((s) => s.kind === kind),
    [strips],
  );

  // Drag-to-create on a boundary-only lane: while pendingDrag is active,
  // track mouse moves anywhere on the page (the user may drag past the
  // lane edge) and commit on mouseup. Threshold 50ms — shorter drags are
  // treated as clicks (no interval created).
  useEffect(() => {
    if (!pendingDrag) return;
    if (!speaker || pxPerSec <= 0) return;
    const onMove = (e: MouseEvent) => {
      const laneEl = laneScrollRefs.current[pendingDrag.kind];
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
  }, [addInterval, duration, pendingDrag, pxPerSec, speaker, stripByKind]);

  if (strips.length === 0 || !audioReady || pxPerSec <= 0 || duration <= 0) {
    return null;
  }

  const innerWidth = Math.max(viewportWidth, pxPerSec * duration);
  const visibleStartSec = Math.max(0, (scrollLeft - VIRTUAL_BUFFER_PX) / pxPerSec);
  const visibleEndSec =
    (scrollLeft + viewportWidth + VIRTUAL_BUFFER_PX) / pxPerSec;

  const commitEdit = (tier: string, sourceIdx: number, text: string) => {
    const trimmed = text.trim();
    if (!speaker) return;
    updateInterval(speaker, tier, sourceIdx, trimmed);
    setEditing(null);
  };

  return (
    <div className="mt-2 space-y-1 px-5">
      {strips.map((strip) => {
        const color = lanes[strip.kind].color;
        const isEmpty = strip.intervals.length === 0;
        let emptyMsg = "";
        if (isEmpty) {
          if (strip.emptyHint) {
            emptyMsg = strip.emptyHint;
          } else if (strip.kind === "stt") {
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
                <div
                  className="relative h-full"
                  style={{ width: innerWidth }}
                  onMouseDown={(e) => {
                    // Drag-to-create on boundary-only lanes (Words / BND).
                    // Only fires on empty timeline space — clicks on
                    // existing interval buttons are stopped at the button
                    // handler (stopPropagation on those covers it).
                    if (!strip.boundaryOnly) return;
                    if (!speaker) return;
                    if (pxPerSec <= 0) return;
                    if (e.button !== 0) return;
                    const target = e.target as HTMLElement | null;
                    if (target?.closest("button")) return;
                    const tier = strip.tier ?? strip.kind;
                    const sec = Math.max(
                      0,
                      Math.min(
                        duration,
                        (e.nativeEvent as MouseEvent).offsetX / pxPerSec,
                      ),
                    );
                    setPendingDrag({
                      kind: strip.kind,
                      tier,
                      startSec: sec,
                      endSec: sec,
                    });
                    e.preventDefault();
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
                    const showLabel =
                      !strip.boundaryOnly && width >= MIN_LABEL_WIDTH_PX;
                    const isEditable = sourceIdx !== undefined;
                    const tierName = strip.tier ?? strip.kind;
                    const isSelected =
                      isEditable &&
                      selectedInterval?.speaker === speaker &&
                      selectedInterval?.tier === tierName &&
                      selectedInterval?.index === sourceIdx;
                    const isEditing =
                      isEditable &&
                      editing?.kind === strip.kind &&
                      editing?.index === sourceIdx;
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
                          ref={editRef}
                          contentEditable
                          suppressContentEditableWarning
                          onMouseDown={(e) => e.stopPropagation()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              commitEdit(
                                tierName,
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
                              tierName,
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
                        // Stop propagation so the lane's drag-to-create
                        // handler doesn't fire when the user clicks on an
                        // existing interval.
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isEditable && sourceIdx !== undefined) {
                            setSelectedInterval({
                              speaker,
                              tier: tierName,
                              index: sourceIdx,
                            });
                          }
                          onSeek?.(iv.start);
                        }}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          if (!isEditable || sourceIdx === undefined) return;
                          // Boundary-only lanes have no text to edit;
                          // double-click is a no-op on Words/BND.
                          if (strip.boundaryOnly) return;
                          if (strip.needsMigration) strip.migrate?.();
                          setEditing({ kind: strip.kind, index: sourceIdx });
                        }}
                        onContextMenu={(e) => {
                          if (!isEditable || sourceIdx === undefined) return;
                          e.preventDefault();
                          e.stopPropagation();
                          if (strip.needsMigration) strip.migrate?.();
                          setSelectedInterval({
                            speaker,
                            tier: tierName,
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
                        title={
                          strip.boundaryOnly
                            ? `${iv.start.toFixed(3)}–${iv.end.toFixed(3)} s${
                                iv.manuallyAdjusted ? " · manually adjusted" : ""
                              }`
                            : `${iv.start.toFixed(3)}–${iv.end.toFixed(3)} s · ${iv.text}`
                        }
                        aria-label={`${strip.label} ${iv.start.toFixed(2)}s${
                          iv.text ? `: ${iv.text}` : ""
                        }`}
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
        const strip = stripByKind(menu.kind);
        const tierName = strip?.tier ?? menu.kind;
        const target = record?.tiers?.[tierName]?.intervals?.[menu.index];
        if (!target) return null;
        const boundaryOnly = !!strip?.boundaryOnly;
        return (
          <ContextMenu
            x={menu.x}
            y={menu.y}
            laneLabel={LANE_LABELS[menu.kind]}
            start={target.start}
            end={target.end}
            onEdit={
              boundaryOnly
                ? null
                : () => {
                    setEditing({ kind: menu.kind, index: menu.index });
                    setMenu(null);
                  }
            }
            onSplit={() => {
              const ws = wsRef.current;
              const t = ws?.getCurrentTime() ?? 0;
              splitInterval(speaker, tierName, menu.index, t);
              setMenu(null);
            }}
            onMerge={() => {
              mergeIntervals(speaker, tierName, menu.index);
              setMenu(null);
            }}
            onDelete={() => {
              removeInterval(speaker, tierName, menu.index);
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
  /** When null, the "Edit text" menu item is omitted — boundary-only
   * lanes (Words / BND) have no text content to edit. */
  onEdit: (() => void) | null;
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
      {onEdit && <MenuItem label="Edit text" hint="dbl-click" onClick={onEdit} />}
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
