import { create } from "zustand";
import type {
  AnnotationRecord,
  AnnotationInterval,
  ConfirmedAnchor,
  SttSegment,
} from "../api/types";
import { getAnnotation, saveAnnotation } from "../api/client";
import {
  applyAddInterval,
  applyMergeIntervals,
  applyRemoveInterval,
  applySetInterval,
  applySplitInterval,
  applyUpdateInterval,
  applyUpdateIntervalTimes,
} from "./annotationStoreIntervals";
import {
  blankRecord,
  CANONICAL_TIER_ORDER,
  deepClone,
  ensureCanonicalTiers,
  nowIsoUtc,
  tierLabel,
} from "./annotationStoreShared";
import {
  emptyHistory,
  popRedoDelta,
  popUndoDelta,
  pushHistoryDelta,
} from "./annotationStoreHistory";
import type { SpeakerHistory } from "./annotationStoreHistory";

/* ------------------------------------------------------------------ */
/*  Debounced auto-save                                                */
/* ------------------------------------------------------------------ */

const autosaveTimers: Record<string, ReturnType<typeof setTimeout>> = {};

function scheduleAutosave(speaker: string) {
  if (autosaveTimers[speaker]) clearTimeout(autosaveTimers[speaker]);
  autosaveTimers[speaker] = setTimeout(async () => {
    try {
      await useAnnotationStore.getState().saveSpeaker(speaker);
    } catch (err) {
      console.warn("[annotationStore] autosave failed:", err);
    }
  }, 2000);
}

/* ------------------------------------------------------------------ */
/*  Store interface                                                    */
/* ------------------------------------------------------------------ */

interface AnnotationStore {
  records: Record<string, AnnotationRecord>;
  dirty: Record<string, boolean>;
  loading: Record<string, boolean>;
  /** Per-speaker undo/redo stacks. Session-only, capped at 50 per stack.
   * Cleared whenever a record is loaded fresh from the backend. */
  histories: Record<string, SpeakerHistory>;

  loadSpeaker: (speaker: string) => Promise<void>;
  saveSpeaker: (speaker: string) => Promise<void>;
  setInterval: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  updateInterval: (speaker: string, tier: string, index: number, text: string) => void;
  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  removeInterval: (speaker: string, tier: string, index: number) => void;
  /** Retime a single interval on one tier. Use this for drag-resize and
   * numeric timestamp edits on a specific lane interval (the cross-tier
   * variant is moveIntervalAcrossTiers). */
  updateIntervalTimes: (
    speaker: string,
    tier: string,
    index: number,
    start: number,
    end: number,
  ) => void;
  /** Merge interval `index` with `index + 1` on the same tier. Both must be
   * adjacent (the gap, if any, is absorbed). Texts are joined with a space. */
  mergeIntervals: (speaker: string, tier: string, index: number) => void;
  /** Split interval `index` at `splitTime` (must lie strictly inside the
   * interval). Original text stays on the left half; right half starts empty. */
  splitInterval: (
    speaker: string,
    tier: string,
    index: number,
    splitTime: number,
  ) => void;
  /** One-time migration: copy the API-cached STT segments for `speaker`
   * into `record.tiers.stt` so STT intervals become first-class editable
   * entries (same affordances as IPA/ORTH). No-op if the tier already has
   * entries. Called lazily on first STT double-click / right-click. */
  ensureSttTier: (speaker: string, segments: SttSegment[]) => void;
  /** One-time migration: flatten Tier 1 word-level boundaries from the API
   * STT cache into ``record.tiers.stt_words`` so the Words lane becomes
   * editable (drag, split, merge, delete, add-in-gap). No-op if the tier
   * already has entries. Called lazily on first edit/add interaction. */
  ensureSttWordsTier: (
    speaker: string,
    segments: SttSegment[],
  ) => void;
  /** Persist a confirmed lexical anchor for a concept on this speaker.
   * Lives in the `confirmed_anchors` sidecar, NOT in any tier — keeps
   * Praat round-trips clean. Pass `null` to clear an existing anchor. */
  setConfirmedAnchor: (
    speaker: string,
    conceptId: string,
    anchor: ConfirmedAnchor | null,
  ) => void;
  /**
   * Retime a lexeme across every tier. Finds the interval that matches
   * (oldStart, oldEnd) within a 1ms tolerance on each tier and rewrites its
   * start/end to (newStart, newEnd), keeping the text. Intended for the
   * concept-timestamp editor in Annotate mode, where the concept interval
   * and its co-timed ipa/ortho/speaker intervals move together.
   * Every moved interval is flagged ``manuallyAdjusted`` so future global
   * offset passes skip it.
   */
  moveIntervalAcrossTiers: (
    speaker: string,
    oldStart: number,
    oldEnd: number,
    newStart: number,
    newEnd: number,
  ) => number;
  /** Flag every interval across every tier whose (start,end) matches the
   * given (start,end) within 1ms as ``manuallyAdjusted``. Called after the
   * user captures a manual-anchor offset pair for a lexeme — the capture
   * itself is an assertion that this lexeme's timing is verified, so a
   * subsequent global offset should not shift it. Returns the count of
   * intervals flagged. */
  markLexemeManuallyAdjusted: (
    speaker: string,
    start: number,
    end: number,
  ) => number;

  /** Pop the most recent undo entry for `speaker`, restore that snapshot,
   * and push the current state onto the redo stack. Returns the label of
   * the undone op (for a toast) or `null` if nothing to undo. */
  undo: (speaker: string) => string | null;
  /** Symmetric to `undo`. */
  redo: (speaker: string) => string | null;
}

export const useAnnotationStore = create<AnnotationStore>()((set, get) => ({
  records: {},
  dirty: {},
  loading: {},
  histories: {},

  loadSpeaker: async (speaker: string) => {
    const state = get();
    if (state.records[speaker] && !state.dirty[speaker]) return;

    set((s) => ({ loading: { ...s.loading, [speaker]: true } }));

    try {
      const record = ensureCanonicalTiers(await getAnnotation(speaker));
      set((s) => ({
        records: { ...s.records, [speaker]: record },
        dirty: { ...s.dirty, [speaker]: false },
        loading: { ...s.loading, [speaker]: false },
        histories: { ...s.histories, [speaker]: emptyHistory() },
      }));
    } catch {
      // API failed — try localStorage fallback
      const lsKey = `parse-annotations-${speaker}`;
      let record: AnnotationRecord;
      try {
        const raw = localStorage.getItem(lsKey);
        if (raw) {
          record = ensureCanonicalTiers(JSON.parse(raw) as AnnotationRecord);
        } else {
          record = blankRecord(speaker);
        }
      } catch {
        record = blankRecord(speaker);
      }
      set((s) => ({
        records: { ...s.records, [speaker]: record },
        dirty: { ...s.dirty, [speaker]: false },
        loading: { ...s.loading, [speaker]: false },
        histories: { ...s.histories, [speaker]: emptyHistory() },
      }));
    }
  },

  saveSpeaker: async (speaker: string) => {
    const state = get();
    const record = state.records[speaker];
    if (!record) throw new Error(`No record loaded for speaker: ${speaker}`);

    await saveAnnotation(speaker, record);
    set((s) => ({ dirty: { ...s.dirty, [speaker]: false } }));

    const lsKey = `parse-annotations-${speaker}`;
    try {
      localStorage.setItem(lsKey, JSON.stringify(record));
    } catch {
      // localStorage full or unavailable — ignore
    }
  },

  setInterval: (speaker: string, tier: string, interval: AnnotationInterval) => {
    const state = get();
    const pre = state.records[speaker] ?? blankRecord(speaker);
    const next = applySetInterval(pre, tier, interval);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `save ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  updateInterval: (speaker: string, tier: string, index: number, text: string) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const next = applyUpdateInterval(pre, tier, index, text);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `text edit (${tierLabel(tier)})`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const next = applyAddInterval(pre, tier, interval);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `add ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  removeInterval: (speaker: string, tier: string, index: number) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const next = applyRemoveInterval(pre, tier, index);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `delete ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  updateIntervalTimes: (speaker, tier, index, start, end) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const next = applyUpdateIntervalTimes(pre, tier, index, start, end);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `retime ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  mergeIntervals: (speaker, tier, index) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const next = applyMergeIntervals(pre, tier, index);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `merge with next (${tierLabel(tier)})`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  splitInterval: (speaker, tier, index, splitTime) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const next = applySplitInterval(pre, tier, index, splitTime);
    if (!next) return;

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, `split (${tierLabel(tier)})`),
      records: { ...s.records, [speaker]: next },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  ensureSttTier: (speaker, segments) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;
    // Idempotent: if the tier already has entries, nothing to migrate.
    if ((pre.tiers.stt?.intervals.length ?? 0) > 0) return;
    if (!Array.isArray(segments) || segments.length === 0) return;

    const clone = deepClone(pre);
    if (!clone.tiers.stt) {
      clone.tiers.stt = {
        name: "stt",
        display_order: CANONICAL_TIER_ORDER.stt,
        intervals: [],
      };
    }
    // Preserve caller order (STT segments arrive sorted from the API). Copy
    // all segments verbatim — empty-text segments are filtered at render
    // time, not here, so indices stay stable for the "edit the segment I
    // just double-clicked" flow.
    clone.tiers.stt.intervals = segments.map((s) => ({
      start: s.start,
      end: s.end,
      text: s.text,
    }));
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, "enable STT editing"),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  ensureSttWordsTier: (speaker, segments) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;
    if ((pre.tiers.stt_words?.intervals.length ?? 0) > 0) return;
    if (!Array.isArray(segments) || segments.length === 0) return;

    // Flatten segments[].words[] preserving source order. Words store
    // empty text — boundary-only lane semantics. Skip degenerate
    // start==end==0 placeholders (Whisper emits these for the first
    // word of a segment when word_timestamps fails on it).
    const flat: AnnotationInterval[] = [];
    for (const seg of segments) {
      const words = (seg as SttSegment).words ?? [];
      for (const w of words) {
        if (typeof w.start !== "number" || typeof w.end !== "number") continue;
        if (w.start === 0 && w.end === 0) continue;
        flat.push({ start: w.start, end: w.end, text: "" });
      }
    }
    if (flat.length === 0) return;

    const clone = deepClone(pre);
    if (!clone.tiers.stt_words) {
      // No canonical order for stt_words — append at end. Praat export
      // falls back to default_order=9999 cleanly.
      const maxOrder = Math.max(
        0,
        ...Object.values(clone.tiers).map((t) => t.display_order),
      );
      clone.tiers.stt_words = {
        name: "stt_words",
        display_order: maxOrder + 1,
        intervals: [],
      };
    }
    clone.tiers.stt_words.intervals = flat;
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, "enable Words editing"),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  setConfirmedAnchor: (speaker, conceptId, anchor) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const clone = deepClone(pre);
    const existing = { ...(clone.confirmed_anchors ?? {}) };
    const key = String(conceptId);
    if (anchor === null) {
      delete existing[key];
    } else {
      existing[key] = { ...anchor };
    }
    clone.confirmed_anchors = existing;
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      histories: pushHistoryDelta(
        s.histories,
        speaker,
        pre,
        anchor === null ? "clear concept anchor" : "confirm concept anchor",
      ),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  moveIntervalAcrossTiers: (speaker, oldStart, oldEnd, newStart, newEnd) => {
    if (!Number.isFinite(newStart) || !Number.isFinite(newEnd)) return 0;
    if (newEnd < newStart) return 0;

    const state = get();
    const pre = state.records[speaker];
    if (!pre) return 0;

    const clone = deepClone(pre);
    const tol = 0.001;
    let moved = 0;
    for (const tier of Object.values(clone.tiers)) {
      const idx = tier.intervals.findIndex(
        (it) => Math.abs(it.start - oldStart) < tol && Math.abs(it.end - oldEnd) < tol,
      );
      if (idx < 0) continue;
      tier.intervals[idx] = {
        ...tier.intervals[idx],
        start: newStart,
        end: newEnd,
        manuallyAdjusted: true,
      };
      tier.intervals.sort((a, b) => a.start - b.start);
      moved += 1;
    }
    if (moved === 0) return 0;
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, "retime lexeme"),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
    return moved;
  },

  markLexemeManuallyAdjusted: (speaker, start, end) => {
    if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;

    const state = get();
    const pre = state.records[speaker];
    if (!pre) return 0;

    const clone = deepClone(pre);
    const tol = 0.001;
    let flagged = 0;
    for (const tier of Object.values(clone.tiers)) {
      for (let i = 0; i < tier.intervals.length; i += 1) {
        const it = tier.intervals[i];
        if (Math.abs(it.start - start) < tol && Math.abs(it.end - end) < tol) {
          if (!it.manuallyAdjusted) {
            tier.intervals[i] = { ...it, manuallyAdjusted: true };
          }
          flagged += 1;
        }
      }
    }
    if (flagged === 0) return 0;
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      histories: pushHistoryDelta(s.histories, speaker, pre, "mark lexeme manually adjusted"),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
    return flagged;
  },

  undo: (speaker) => {
    const state = get();
    const delta = popUndoDelta(state.histories, state.records, speaker);
    if (!delta) return null;

    set((s) => ({
      records: { ...s.records, [speaker]: delta.record },
      dirty: { ...s.dirty, [speaker]: true },
      histories: delta.histories,
    }));
    scheduleAutosave(speaker);
    return delta.label;
  },

  redo: (speaker) => {
    const state = get();
    const delta = popRedoDelta(state.histories, state.records, speaker);
    if (!delta) return null;

    set((s) => ({
      records: { ...s.records, [speaker]: delta.record },
      dirty: { ...s.dirty, [speaker]: true },
      histories: delta.histories,
    }));
    scheduleAutosave(speaker);
    return delta.label;
  },
}));
