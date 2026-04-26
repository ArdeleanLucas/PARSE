import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type WaveSurfer from "wavesurfer.js";
import { useAnnotationStore } from "../../stores/annotationStore";
import {
  useTranscriptionLanesStore,
  LANE_LABELS,
  type LaneKind,
} from "../../stores/transcriptionLanesStore";
import type { AnnotationInterval, SttSegment } from "../../api/types";
import { TranscriptionLaneRow, type LaneStrip } from "./TranscriptionLaneRow";
import { TranscriptionLaneToolbar } from "./TranscriptionLaneToolbar";
import { useTranscriptionLaneBoundaryEdit } from "./useTranscriptionLaneBoundaryEdit";
import { useTranscriptionLaneInlineEdit } from "./useTranscriptionLaneInlineEdit";
interface TranscriptionLanesProps {
  speaker: string;
  wsRef: React.RefObject<WaveSurfer | null>;
  audioReady: boolean;
  onSeek?: (timeSec: number) => void;
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

export const LABEL_COL_PX = 56;
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
  const [menu, setMenu] = useState<
    { kind: LaneKind; index: number; x: number; y: number } | null
  >(null);
  const editRef = useRef<HTMLSpanElement | null>(null);
  const { beginIntervalEdit, commitEdit, editing, setEditing } = useTranscriptionLaneInlineEdit({
    editRef,
    speaker,
    updateInterval,
  });

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

  const { beginDrag, pendingDrag } = useTranscriptionLaneBoundaryEdit({
    addInterval,
    duration,
    laneScrollRefs,
    pxPerSec,
    speaker,
    stripByKind,
  });

  if (strips.length === 0 || !audioReady || pxPerSec <= 0 || duration <= 0) {
    return null;
  }

  const innerWidth = Math.max(viewportWidth, pxPerSec * duration);
  const visibleStartSec = Math.max(0, (scrollLeft - VIRTUAL_BUFFER_PX) / pxPerSec);
  const visibleEndSec =
    (scrollLeft + viewportWidth + VIRTUAL_BUFFER_PX) / pxPerSec;

  const seekInterval = (
    iv: LaneStrip["intervals"][number],
    sourceIdx: number | undefined,
    tierName: string,
  ) => {
    if (sourceIdx !== undefined) {
      setSelectedInterval({
        speaker,
        tier: tierName,
        index: sourceIdx,
      });
    }
    onSeek?.(iv.start);
  };

  const openContextMenu = (
    strip: LaneStrip,
    sourceIdx: number,
    event: React.MouseEvent<HTMLButtonElement>,
  ) => {
    if (strip.needsMigration) strip.migrate?.();
    const tierName = strip.tier ?? strip.kind;
    setSelectedInterval({
      speaker,
      tier: tierName,
      index: sourceIdx,
    });
    setMenu({
      kind: strip.kind,
      index: sourceIdx,
      x: event.clientX,
      y: event.clientY,
    });
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
          <TranscriptionLaneRow
            key={strip.kind}
            color={color}
            editing={editing}
            emptyMsg={emptyMsg}
            firstIdx={firstIdx}
            innerWidth={innerWidth}
            isEmpty={isEmpty}
            pendingDrag={pendingDrag}
            pxPerSec={pxPerSec}
            selectedInterval={selectedInterval}
            setEditing={setEditing}
            setEditRef={(element) => {
              editRef.current = element;
            }}
            setLaneScrollRef={(kind, element) => {
              laneScrollRefs.current[kind] = element;
            }}
            showEmptyHint={isEmpty}
            speaker={speaker}
            strip={strip}
            visible={visible}
            visibleSourceIndices={visibleSourceIndices}
            onBeginDrag={beginDrag}
            onCommitEdit={commitEdit}
            onContextMenu={openContextMenu}
            onDoubleClickInterval={beginIntervalEdit}
            onSeekInterval={seekInterval}
          />
        );
      })}

      {menu && (() => {
        const strip = stripByKind(menu.kind);
        const tierName = strip?.tier ?? menu.kind;
        const target = record?.tiers?.[tierName]?.intervals?.[menu.index];
        if (!target) return null;
        const boundaryOnly = !!strip?.boundaryOnly;
        return (
          <TranscriptionLaneToolbar
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
