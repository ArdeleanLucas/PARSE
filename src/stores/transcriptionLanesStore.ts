import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { SttSegment } from "../api/types";
import { getSttSegments } from "../api/client";

// Lane identities visible in the transcription viewer. The visual top-to-bottom
// order is hard-coded in TranscriptionLanes.tsx (LANE_ORDER), independent of
// the canonical numeric display_order used for Praat export.
export type LaneKind = "ipa_phone" | "ipa" | "stt" | "ortho";

export interface LaneConfig {
  visible: boolean;
  color: string;
}

/** Single-interval selection used by the inline editor / segment toolbar. */
export interface SelectedInterval {
  speaker: string;
  tier: LaneKind;
  index: number;
}

interface PersistedState {
  lanes: Record<LaneKind, LaneConfig>;
}

interface TranscriptionLanesStore extends PersistedState {
  sttBySpeaker: Record<string, SttSegment[]>;
  sttStatus: Record<string, "idle" | "loading" | "loaded" | "error">;
  selectedInterval: SelectedInterval | null;

  toggleLane: (kind: LaneKind) => void;
  setLaneColor: (kind: LaneKind, color: string) => void;

  ensureStt: (speaker: string) => Promise<void>;
  reloadStt: (speaker: string) => Promise<void>;

  setSelectedInterval: (sel: SelectedInterval | null) => void;
}

export const LANE_LABELS: Record<LaneKind, string> = {
  ipa_phone: "Phones",
  ipa: "IPA",
  stt: "STT",
  ortho: "ORTH",
};

const DEFAULT_LANES: Record<LaneKind, LaneConfig> = {
  ipa_phone: { visible: true, color: "#8b5cf6" }, // violet — phone-level IPA
  ipa: { visible: true, color: "#059669" },       // emerald — word/lexeme IPA
  stt: { visible: true, color: "#6366f1" },       // indigo
  ortho: { visible: true, color: "#d97706" },     // amber
  // To surface the sentence tier as a lane later: add "sentence" to LaneKind,
  // LANE_LABELS above, LANE_ORDER in TranscriptionLanes.tsx, and uncomment:
  // sentence: { visible: false, color: "#0ea5e9" }, // sky — sentence grouping
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
      selectedInterval: null,

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

      setSelectedInterval: (sel) => set({ selectedInterval: sel }),
    }),
    {
      name: "parse.transcription-lanes",
      // Bumped to v2 when ipa_phone was added — old persisted lane configs lack
      // the new key. The migrate fn fills it in with the default rather than
      // letting the lookup return undefined and crash the renderer.
      storage: createJSONStorage(() => localStorage),
      partialize: (state): PersistedState => ({ lanes: state.lanes }),
      version: 2,
      migrate: (persisted: unknown, fromVersion: number): PersistedState => {
        const fallback: PersistedState = { lanes: DEFAULT_LANES };
        if (!persisted || typeof persisted !== "object") return fallback;
        const raw = (persisted as { lanes?: Partial<Record<LaneKind, LaneConfig>> }).lanes ?? {};
        if (fromVersion < 2) {
          return {
            lanes: {
              ipa_phone: raw.ipa_phone ?? DEFAULT_LANES.ipa_phone,
              ipa: raw.ipa ?? DEFAULT_LANES.ipa,
              stt: raw.stt ?? DEFAULT_LANES.stt,
              ortho: raw.ortho ?? DEFAULT_LANES.ortho,
            },
          };
        }
        return { lanes: { ...DEFAULT_LANES, ...raw } as Record<LaneKind, LaneConfig> };
      },
    },
  ),
);
