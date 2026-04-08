import { create } from "zustand";
import type { AnnotationRecord, AnnotationInterval } from "../api/types";
import { getAnnotation, saveAnnotation } from "../api/client";

/* ------------------------------------------------------------------ */
/*  Helpers (module-scope, not exported)                               */
/* ------------------------------------------------------------------ */

const CANONICAL_TIER_ORDER: Record<string, number> = {
  ipa: 1,
  ortho: 2,
  concept: 3,
  speaker: 4,
};

function nowIsoUtc(): string {
  return new Date().toISOString();
}

function blankRecord(speaker: string): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa: { name: "ipa", display_order: 1, intervals: [] },
      ortho: { name: "ortho", display_order: 2, intervals: [] },
      concept: { name: "concept", display_order: 3, intervals: [] },
      speaker: { name: "speaker", display_order: 4, intervals: [] },
    },
    created_at: nowIsoUtc(),
    modified_at: nowIsoUtc(),
    source_wav: "",
  };
}

function deepClone<T>(val: T): T {
  return JSON.parse(JSON.stringify(val));
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

  loadSpeaker: (speaker: string) => Promise<void>;
  saveSpeaker: (speaker: string) => Promise<void>;
  updateInterval: (speaker: string, tier: string, index: number, text: string) => void;
  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => void;
  removeInterval: (speaker: string, tier: string, index: number) => void;
}

export const useAnnotationStore = create<AnnotationStore>()((set, get) => ({
  records: {},
  dirty: {},
  loading: {},

  loadSpeaker: async (speaker: string) => {
    const state = get();
    if (state.records[speaker] && !state.dirty[speaker]) return;

    set((s) => ({ loading: { ...s.loading, [speaker]: true } }));

    try {
      const record = await getAnnotation(speaker);
      set((s) => ({
        records: { ...s.records, [speaker]: record },
        dirty: { ...s.dirty, [speaker]: false },
        loading: { ...s.loading, [speaker]: false },
      }));
    } catch {
      // API failed — try localStorage fallback
      const lsKey = `parse-annotations-${speaker}`;
      let record: AnnotationRecord;
      try {
        const raw = localStorage.getItem(lsKey);
        if (raw) {
          record = JSON.parse(raw) as AnnotationRecord;
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

  updateInterval: (speaker: string, tier: string, index: number, text: string) => {
    const state = get();
    const record = state.records[speaker];
    if (!record) return;
    if (!record.tiers[tier]) return;
    if (index < 0 || index >= record.tiers[tier].intervals.length) return;

    const clone = deepClone(record);
    clone.tiers[tier].intervals[index].text = text;
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  addInterval: (speaker: string, tier: string, interval: AnnotationInterval) => {
    if (!Number.isFinite(interval.start) || !Number.isFinite(interval.end)) return;
    if (interval.end < interval.start) return;

    const state = get();
    const record = state.records[speaker];
    if (!record) return;

    const clone = deepClone(record);

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
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },

  removeInterval: (speaker: string, tier: string, index: number) => {
    const state = get();
    const record = state.records[speaker];
    if (!record) return;
    if (!record.tiers[tier]) return;
    if (index < 0 || index >= record.tiers[tier].intervals.length) return;

    const clone = deepClone(record);
    clone.tiers[tier].intervals.splice(index, 1);
    clone.modified_at = nowIsoUtc();

    set((s) => ({
      records: { ...s.records, [speaker]: clone },
      dirty: { ...s.dirty, [speaker]: true },
    }));
    scheduleAutosave(speaker);
  },
}));
