import { getAnnotation, saveAnnotation } from "@/api/client";
import type { AnnotationRecord } from "../../api/types";
import { emptyHistory } from "../annotationStoreHistory";
import { blankRecord, ensureCanonicalTiers } from "../annotationStoreShared";
import { selectSpeakerDirty, selectSpeakerRecord } from "./selectors";
import type {
  AnnotationStoreGet,
  AnnotationStorePersistenceSlice,
  AnnotationStoreSet,
  SaveSpeakerResult,
  ScheduleAnnotationAutosave,
} from "./types";

const autosaveTimers: Record<string, ReturnType<typeof setTimeout>> = {};

export function createAnnotationAutosaveScheduler(get: AnnotationStoreGet): ScheduleAnnotationAutosave {
  return (speaker: string) => {
    if (autosaveTimers[speaker]) clearTimeout(autosaveTimers[speaker]);
    autosaveTimers[speaker] = setTimeout(async () => {
      try {
        await get().saveSpeaker(speaker);
      } catch (err) {
        console.warn("[annotationStore] autosave failed:", err);
      }
    }, 2000);
  };
}


function serializedIntervals(record: AnnotationRecord | null | undefined, tier: string): string {
  return JSON.stringify(record?.tiers?.[tier]?.intervals ?? []);
}

function changedIntervalTiers(before: AnnotationRecord | null | undefined, after: AnnotationRecord): string[] {
  const tierNames = new Set([
    ...Object.keys(before?.tiers ?? {}),
    ...Object.keys(after.tiers ?? {}),
  ]);
  return [...tierNames]
    .filter((tier) => serializedIntervals(before, tier) !== serializedIntervals(after, tier))
    .sort((left, right) => {
      const leftOrder = after.tiers[left]?.display_order ?? before?.tiers?.[left]?.display_order ?? Number.MAX_SAFE_INTEGER;
      const rightOrder = after.tiers[right]?.display_order ?? before?.tiers?.[right]?.display_order ?? Number.MAX_SAFE_INTEGER;
      return leftOrder - rightOrder || left.localeCompare(right);
    });
}

function resolveLocalFallbackRecord(speaker: string): AnnotationRecord {
  const lsKey = `parse-annotations-${speaker}`;
  try {
    const raw = localStorage.getItem(lsKey);
    if (raw) {
      return ensureCanonicalTiers(JSON.parse(raw) as AnnotationRecord);
    }
  } catch {
    // localStorage unavailable or invalid JSON — fall back to blank record
  }
  return blankRecord(speaker);
}

export function createAnnotationPersistenceSlice(
  set: AnnotationStoreSet,
  get: AnnotationStoreGet,
): AnnotationStorePersistenceSlice {
  return {
    loadSpeaker: async (speaker: string) => {
      const state = get();
      if (selectSpeakerRecord(state, speaker) && !selectSpeakerDirty(state, speaker)) return;

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
        const record = resolveLocalFallbackRecord(speaker);
        set((s) => ({
          records: { ...s.records, [speaker]: record },
          dirty: { ...s.dirty, [speaker]: false },
          loading: { ...s.loading, [speaker]: false },
          histories: { ...s.histories, [speaker]: emptyHistory() },
        }));
      }
    },

    saveSpeaker: async (speaker: string, baseline?: AnnotationRecord | null): Promise<SaveSpeakerResult> => {
      const record = selectSpeakerRecord(get(), speaker);
      if (!record) throw new Error(`No record loaded for speaker: ${speaker}`);

      const savedRecord = ensureCanonicalTiers((await saveAnnotation(speaker, record)) ?? record);
      const changedTiers = changedIntervalTiers(baseline ?? record, savedRecord);
      set((s) => ({
        records: { ...s.records, [speaker]: savedRecord },
        dirty: { ...s.dirty, [speaker]: false },
      }));

      const lsKey = `parse-annotations-${speaker}`;
      try {
        localStorage.setItem(lsKey, JSON.stringify(savedRecord));
      } catch {
        // localStorage full or unavailable — ignore
      }
      return { record: savedRecord, changedTiers };
    },
  };
}
