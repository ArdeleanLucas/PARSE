import { create } from "zustand";
import { createAnnotationActionsSlice } from "./annotation/actions";
import {
  createAnnotationAutosaveScheduler,
  createAnnotationPersistenceSlice,
} from "./annotation/persistence";
import type { AnnotationStore } from "./annotation/types";

export type { AnnotationStore } from "./annotation/types";
export * from "./annotation/selectors";

export const useAnnotationStore = create<AnnotationStore>()((set, get) => {
  const scheduleAutosave = createAnnotationAutosaveScheduler(get);

  return {
    records: {},
    dirty: {},
    loading: {},
    histories: {},
    ...createAnnotationPersistenceSlice(set, get),
    ...createAnnotationActionsSlice(set, get, scheduleAutosave),
  };
});
