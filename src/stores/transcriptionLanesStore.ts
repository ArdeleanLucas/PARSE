import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SttSegment } from "../api/types";
import { getSttSegments } from "../api/client";

export type LaneKind = "stt" | "ipa" | "ortho";

export interface LaneConfig {
  visible: boolean;
  color: string;
}

interface PersistedState {
  lanes: Record<LaneKind, LaneConfig>;
}

interface TranscriptionLanesStore extends PersistedState {
  sttBySpeaker: Record<string, SttSegment[]>;
  sttStatus: Record<string, "idle" | "loading" | "loaded" | "error">;

  toggleLane: (kind: LaneKind) => void;
  setLaneColor: (kind: LaneKind, color: string) => void;

  ensureStt: (speaker: string) => Promise<void>;
  reloadStt: (speaker: string) => Promise<void>;
}

const DEFAULT_LANES: Record<LaneKind, LaneConfig> = {
  stt: { visible: true, color: "#6366f1" },   // indigo
  ipa: { visible: true, color: "#059669" },   // emerald
  ortho: { visible: true, color: "#d97706" }, // amber
};

async function fetchSttInto(
  speaker: string,
  set: (
    updater: (s: TranscriptionLanesStore) => Partial<TranscriptionLanesStore>,
  ) => void,
): Promise<void> {
  set((s) => ({
    sttStatus: { ...s.sttStatus, [speaker]: "loading" },
  }));
  try {
    const payload = await getSttSegments(speaker);
    const segments = Array.isArray(payload?.segments) ? payload.segments : [];
    set((s) => ({
      sttBySpeaker: { ...s.sttBySpeaker, [speaker]: segments },
      sttStatus: { ...s.sttStatus, [speaker]: "loaded" },
    }));
  } catch {
    set((s) => ({
      sttBySpeaker: { ...s.sttBySpeaker, [speaker]: [] },
      sttStatus: { ...s.sttStatus, [speaker]: "error" },
    }));
  }
}

export const useTranscriptionLanesStore = create<TranscriptionLanesStore>()(
  persist(
    (set, get) => ({
      lanes: DEFAULT_LANES,
      sttBySpeaker: {},
      sttStatus: {},

      toggleLane: (kind) =>
        set((s) => ({
          lanes: {
            ...s.lanes,
            [kind]: { ...s.lanes[kind], visible: !s.lanes[kind].visible },
          },
        })),

      setLaneColor: (kind, color) =>
        set((s) => ({
          lanes: { ...s.lanes, [kind]: { ...s.lanes[kind], color } },
        })),

      ensureStt: async (speaker) => {
        if (!speaker) return;
        const status = get().sttStatus[speaker];
        if (status === "loading" || status === "loaded") return;
        await fetchSttInto(speaker, set);
      },

      reloadStt: async (speaker) => {
        if (!speaker) return;
        await fetchSttInto(speaker, set);
      },
    }),
    {
      name: "parse.transcription-lanes",
      storage: createJSONStorage(() => localStorage),
      partialize: (state): PersistedState => ({ lanes: state.lanes }),
      version: 1,
    },
  ),
);
