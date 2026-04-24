import { create } from "zustand";
import type {
  AnnotationRecord,
  AnnotationInterval,
  ConfirmedAnchor,
  SttSegment,
} from "../api/types";
import { getAnnotation, saveAnnotation } from "../api/client";

/* ------------------------------------------------------------------ */
/*  Helpers (module-scope, not exported)                               */
/* ------------------------------------------------------------------ */

// Canonical tier ordering. Numeric order is used for backend/Praat sort only;
// the visual lane order in TranscriptionLanes.tsx is hard-coded separately.
// Adding a new tier? Update _CANONICAL_DISPLAY_ORDERS in python/textgrid_io.py
// to match, or Praat exports will fall back to default_order=9999.
const CANONICAL_TIER_ORDER: Record<string, number> = {
  ipa_phone: 1,   // phone-level IPA (wav2vec2 output, lane-visible)
  ipa: 2,         // word/lexeme-level IPA (lane-visible)
  ortho: 3,       // orthographic transcription, coarse Whisper segments (lane-visible)
  ortho_words: 4, // word-level ortho from Tier-2 forced alignment (data-only, no lane)
  stt: 5,         // speech-to-text reference (lane-visible)
  concept: 6,     // concept tags
  sentence: 7,    // sentence-level grouping (starts empty)
  speaker: 8,     // speaker turn
};

function nowIsoUtc(): string {
  return new Date().toISOString();
}

function blankRecord(speaker: string): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa_phone:   { name: "ipa_phone",   display_order: 1, intervals: [] },
      ipa:         { name: "ipa",         display_order: 2, intervals: [] },
      ortho:       { name: "ortho",       display_order: 3, intervals: [] },
      ortho_words: { name: "ortho_words", display_order: 4, intervals: [] },
      stt:         { name: "stt",         display_order: 5, intervals: [] },
      concept:     { name: "concept",     display_order: 6, intervals: [] },
      sentence:    { name: "sentence",    display_order: 7, intervals: [] },
      speaker:     { name: "speaker",     display_order: 8, intervals: [] },
    },
    created_at: nowIsoUtc(),
    modified_at: nowIsoUtc(),
    source_wav: "",
  };
}

// Backfill any canonical tiers missing from a loaded record so older
// annotations still get the new ipa_phone/stt/sentence lanes wired up.
function ensureCanonicalTiers(record: AnnotationRecord): AnnotationRecord {
  const tiers = { ...record.tiers };
  let changed = false;
  for (const [name, order] of Object.entries(CANONICAL_TIER_ORDER)) {
    if (!tiers[name]) {
      tiers[name] = { name, display_order: order, intervals: [] };
      changed = true;
    }
  }
  return changed ? { ...record, tiers } : record;
}

function deepClone<T>(val: T): T {
  return JSON.parse(JSON.stringify(val));
}

/* ------------------------------------------------------------------ */
/*  Undo/redo history (session-only, per-speaker)                      */
/* ------------------------------------------------------------------ */

// Deep-cloned pre-mutation snapshots. Session-only — never persisted, cleared
// when a speaker record is loaded/reloaded from the backend. The `label`
// surfaces in toasts ("Undid merge with next").
export interface HistoryEntry {
  snapshot: AnnotationRecord;
  label: string;
}

export interface SpeakerHistory {
  undo: HistoryEntry[];
  redo: HistoryEntry[];
}

// Human-readable tier names for undo/redo labels. Surfaced verbatim in
// toasts ("Undid text edit (IPA)"), so keep these short and matched to the
// LANE_LABELS the user already sees in TranscriptionLanes where possible.
// Unknown/custom tiers fall through to the raw slug, which is still readable
// (e.g. a custom "gloss" tier shows as "Undid text edit (gloss)").
const TIER_LABEL: Record<string, string> = {
  ipa_phone: "Phones",
  ipa: "IPA",
  ortho: "ORTH",
  ortho_words: "ORTH words",
  stt: "STT",
  concept: "Concept",
  sentence: "Sentence",
  speaker: "Speaker",
};

function tierLabel(tier: string): string {
  return TIER_LABEL[tier] ?? tier;
}

// Max undo-stack depth per speaker. Chosen to keep snapshot memory bounded
// for long annotation sessions on large records (a full AnnotationRecord
// with ~5k intervals across tiers is tens of KB; 50 snapshots ≈ a few MB
// per speaker in the worst case).
const HISTORY_CAP = 50;

function emptyHistory(): SpeakerHistory {
  return { undo: [], redo: [] };
}

/** Build a histories delta that pushes `pre` onto the speaker's undo stack
 * and clears redo. Called from inside every mutator with the pre-mutation
 * record so the snapshot captures "the state we're about to leave behind".
 * Returns a Partial<AnnotationStore> fragment ready to spread into set().
 *
 * Overflow behavior: when the undo stack reaches HISTORY_CAP (50), the
 * OLDEST entry is silently dropped (FIFO eviction via `shift()`) so the
 * most recent 50 operations stay undoable. No toast, no throw — the user
 * simply can't Ctrl+Z past the cap. The redo stack is not capped here; it
 * only grows via `undo()` and is naturally bounded by the undo depth. */
function pushHistoryDelta(
  state: { histories: Record<string, SpeakerHistory> },
  speaker: string,
  pre: AnnotationRecord,
  label: string,
): { histories: Record<string, SpeakerHistory> } {
  const prev = state.histories[speaker] ?? emptyHistory();
  const undo = [...prev.undo, { snapshot: deepClone(pre), label }];
  // Drop the oldest snapshot (FIFO) once we exceed HISTORY_CAP. Only one can
  // exceed per push since we append a single entry, so a single shift() is
  // enough — no loop needed.
  if (undo.length > HISTORY_CAP) undo.shift();
  return { histories: { ...state.histories, [speaker]: { undo, redo: [] } } };
}

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
    if (!Number.isFinite(interval.start) || !Number.isFinite(interval.end)) return;
    if (interval.end < interval.start) return;

    const state = get();
    const pre = state.records[speaker] ?? blankRecord(speaker);
    const clone = deepClone(pre);

    if (!clone.tiers[tier]) {
      const maxOrder = Math.max(0, ...Object.values(clone.tiers).map((t) => t.display_order));
      clone.tiers[tier] = {
        name: tier,
        display_order: CANONICAL_TIER_ORDER[tier] ?? maxOrder + 1,
        intervals: [],
      };
    }

    clone.tiers[tier].intervals = clone.tiers[tier].intervals.filter(
      (candidate) => !(Math.abs(candidate.start - interval.start) < 0.001 && Math.abs(candidate.end - interval.end) < 0.001),
    );
    clone.tiers[tier].intervals.push(interval);
    clone.tiers[tier].intervals.sort((a, b) => a.start - b.start);
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `save ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  updateInterval: (speaker: string, tier: string, index: number, text: string) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;
    if (!pre.tiers[tier]) return;
    if (index < 0 || index >= pre.tiers[tier].intervals.length) return;

    const clone = deepClone(pre);
    clone.tiers[tier].intervals[index].text = text;
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `text edit (${tierLabel(tier)})`),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => {
    if (!Number.isFinite(interval.start) || !Number.isFinite(interval.end)) return;
    if (interval.end < interval.start) return;

    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;

    const clone = deepClone(pre);

    if (!clone.tiers[tier]) {
      const maxOrder = Math.max(
        0,
        ...Object.values(clone.tiers).map((t) => t.display_order),
      );
      clone.tiers[tier] = {
        name: tier,
        display_order: CANONICAL_TIER_ORDER[tier] ?? maxOrder + 1,
        intervals: [],
      };
    }

    clone.tiers[tier].intervals.push(interval);
    clone.tiers[tier].intervals.sort((a, b) => a.start - b.start);
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `add ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  removeInterval: (speaker: string, tier: string, index: number) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre) return;
    if (!pre.tiers[tier]) return;
    if (index < 0 || index >= pre.tiers[tier].intervals.length) return;

    const clone = deepClone(pre);
    clone.tiers[tier].intervals.splice(index, 1);
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `delete ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  updateIntervalTimes: (speaker, tier, index, start, end) => {
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    if (end < start) return;

    const state = get();
    const pre = state.records[speaker];
    if (!pre?.tiers[tier]) return;
    if (index < 0 || index >= pre.tiers[tier].intervals.length) return;

    const clone = deepClone(pre);
    const target = clone.tiers[tier].intervals[index];
    clone.tiers[tier].intervals[index] = {
      ...target,
      start,
      end,
      manuallyAdjusted: true,
    };
    clone.tiers[tier].intervals.sort((a, b) => a.start - b.start);
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `retime ${tierLabel(tier)} segment`),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  mergeIntervals: (speaker, tier, index) => {
    const state = get();
    const pre = state.records[speaker];
    if (!pre?.tiers[tier]) return;
    const intervals = pre.tiers[tier].intervals;
    if (index < 0 || index >= intervals.length - 1) return;

    const left = intervals[index];
    const right = intervals[index + 1];
    const mergedText = [left.text, right.text]
      .map((t) => (t ?? "").trim())
      .filter(Boolean)
      .join(" ");

    const clone = deepClone(pre);
    clone.tiers[tier].intervals.splice(index, 2, {
      start: left.start,
      end: right.end,
      text: mergedText,
    });
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `merge with next (${tierLabel(tier)})`),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  splitInterval: (speaker, tier, index, splitTime) => {
    if (!Number.isFinite(splitTime)) return;
    const state = get();
    const pre = state.records[speaker];
    if (!pre?.tiers[tier]) return;
    const intervals = pre.tiers[tier].intervals;
    if (index < 0 || index >= intervals.length) return;

    const target = intervals[index];
    const tol = 0.001;
    if (splitTime <= target.start + tol || splitTime >= target.end - tol) return;

    const clone = deepClone(pre);
    clone.tiers[tier].intervals.splice(
      index,
      1,
      { start: target.start, end: splitTime, text: target.text },
      { start: splitTime, end: target.end, text: "" },
    );
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      ...pushHistoryDelta(s, speaker, pre, `split (${tierLabel(tier)})`),
      records: { ...s.records, [speaker]: clone },
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
      ...pushHistoryDelta(s, speaker, pre, "enable STT editing"),
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
      ...pushHistoryDelta(
        s,
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
      ...pushHistoryDelta(s, speaker, pre, "retime lexeme"),
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
      ...pushHistoryDelta(s, speaker, pre, "mark lexeme manually adjusted"),
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
    return flagged;
  },

  undo: (speaker) => {
    const state = get();
    const hist = state.histories[speaker];
    const current = state.records[speaker];
    if (!hist || hist.undo.length === 0 || !current) return null;

    const entry = hist.undo[hist.undo.length - 1];
    const nextUndo = hist.undo.slice(0, -1);
    // Symmetric: pushing the pre-undo record onto redo lets redo put it back.
    // Reuse the label so the toast reads the same action either direction.
    const nextRedo = [
      ...hist.redo,
      { snapshot: deepClone(current), label: entry.label },
    ];

    set((s) => ({
      records: { ...s.records, [speaker]: entry.snapshot },
      dirty: { ...s.dirty, [speaker]: true },
      histories: {
        ...s.histories,
        [speaker]: { undo: nextUndo, redo: nextRedo },
      },
    }));
    scheduleAutosave(speaker);
    return entry.label;
  },

  redo: (speaker) => {
    const state = get();
    const hist = state.histories[speaker];
    const current = state.records[speaker];
    if (!hist || hist.redo.length === 0 || !current) return null;

    const entry = hist.redo[hist.redo.length - 1];
    const nextRedo = hist.redo.slice(0, -1);
    const nextUndo = [
      ...hist.undo,
      { snapshot: deepClone(current), label: entry.label },
    ];

    set((s) => ({
      records: { ...s.records, [speaker]: entry.snapshot },
      dirty: { ...s.dirty, [speaker]: true },
      histories: {
        ...s.histories,
        [speaker]: { undo: nextUndo, redo: nextRedo },
      },
    }));
    scheduleAutosave(speaker);
    return entry.label;
  },
}));
