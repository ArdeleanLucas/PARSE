import { create } from "zustand";
import type { SttSegment } from "../api/types";
import { getSttSegments } from "../api/client";

export type LaneKind = "stt" | "ipa" | "ortho";

export interface LaneConfig {
  visible: boolean;
  color: string;
}

interface TranscriptionLanesStore {
  lanes: Record<LaneKind, LaneConfig>;
  sttByspeaker: Record<string, SttSegment[]>;
  loadedSpeakers: Record<string, boolean>;

  toggleLane: (kind: LaneKind) => void;
  setLaneColor: (kind: LaneKind, color: string) => void;
  loadStt: (speaker: string) => Promise<void>;
}

const DEFAULT_LANES: Record<LaneKind, LaneConfig> = {
  stt: { visible: false, color: "#6366f1" },   // indigo
  ipa: { visible: true, color: "#059669" },    // emerald
  ortho: { visible: true, color: "#d97706" },  // amber
};

export const useTranscriptionLanesStore = create<TranscriptionLanesStore>()((set, get) => ({
  lanes: DEFAULT_LANES,
  sttByspeaker: {},
  loadedSpeakers: {},

  toggleLane: (kind) =>
    set((s) => ({
      lanes: { ...s.lanes, [kind]: { ...s.lanes[kind], visible: !s.lanes[kind].visible } },
    })),

  setLaneColor: (kind, color) =>
    set((s) => ({
      lanes: { ...s.lanes, [kind]: { ...s.lanes[kind], color } },
    })),

  loadStt: async (speaker) => {
    if (!speaker) return;
    if (get().loadedSpeakers[speaker]) return;
    try {
      const payload = await getSttSegments(speaker);
      const segments = Array.isArray(payload?.segments) ? payload.segments : [];
      set((s) => ({
        sttByspeaker: { ...s.sttByspeaker, [speaker]: segments },
        loadedSpeakers: { ...s.loadedSpeakers, [speaker]: true },
      }));
    } catch {
      set((s) => ({
        sttByspeaker: { ...s.sttByspeaker, [speaker]: [] },
        loadedSpeakers: { ...s.loadedSpeakers, [speaker]: true },
      }));
    }
  },
}));
