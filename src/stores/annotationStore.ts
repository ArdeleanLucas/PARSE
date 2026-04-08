import { create } from "zustand";
import type { AnnotationRecord, AnnotationInterval } from "../api/types";

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

export const useAnnotationStore = create<AnnotationStore>()(() => ({
  records: {},
  dirty: {},
  loading: {},

  // TODO Track A: implement in A2
  loadSpeaker: async (_speaker: string) => {
    throw new Error("Not implemented — Track A A2");
  },
  saveSpeaker: async (_speaker: string) => {
    throw new Error("Not implemented — Track A A2");
  },
  updateInterval: (_speaker: string, _tier: string, _index: number, _text: string) => {
    throw new Error("Not implemented — Track A A2");
  },
  addInterval: (_speaker: string, _tier: string, _interval: AnnotationInterval) => {
    throw new Error("Not implemented — Track A A2");
  },
  removeInterval: (_speaker: string, _tier: string, _index: number) => {
    throw new Error("Not implemented — Track A A2");
  },
}));
