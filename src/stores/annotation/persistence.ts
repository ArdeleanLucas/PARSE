import { getAnnotation, saveAnnotation } from "@/api/client";
import type { AnnotationRecord } from "../../api/types";
import { emptyHistory } from "../annotationStoreHistory";
import { blankRecord, ensureCanonicalTiers } from "../annotationStoreShared";
import { selectSpeakerDirty, selectSpeakerRecord } from "./selectors";
import type {
  AnnotationStoreGet,
  AnnotationStorePersistenceSlice,
  AnnotationStoreSet,
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

    saveSpeaker: async (speaker: string) => {
      const record = selectSpeakerRecord(get(), speaker);
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
  };
}
