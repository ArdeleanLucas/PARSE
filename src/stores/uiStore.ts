import { create } from "zustand";

interface UIStore {
  activeSpeaker: string | null;
  activeConcept: string | null;
  annotatePanel: "annotation" | "transcript" | "suggestions" | "chat";
  comparePanel: "cognate" | "borrowing" | "enrichments" | "tags";
  sidebarOpen: boolean;
  onboardingComplete: boolean;
  selectedSpeakers: string[];

  setActiveSpeaker: (s: string | null) => void;
  setActiveConcept: (c: string | null) => void;
  setAnnotatePanel: (p: UIStore["annotatePanel"]) => void;
  setComparePanel: (p: UIStore["comparePanel"]) => void;
  toggleSidebar: () => void;
  setOnboardingComplete: (v: boolean) => void;
  setSelectedSpeakers: (speakers: string[]) => void;
}

export const useUIStore = create<UIStore>()((set) => ({
  activeSpeaker: null,
  activeConcept: null,
  annotatePanel: "annotation",
  comparePanel: "cognate",
  sidebarOpen: true,
  onboardingComplete: false,
  selectedSpeakers: [],

  setActiveSpeaker: (s) => set({ activeSpeaker: s }),
  setActiveConcept: (c) => set({ activeConcept: c }),
  setAnnotatePanel: (p) => set({ annotatePanel: p }),
  setComparePanel: (p) => set({ comparePanel: p }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setOnboardingComplete: (v) => set({ onboardingComplete: v }),
  setSelectedSpeakers: (speakers) => set({ selectedSpeakers: speakers }),
}));
