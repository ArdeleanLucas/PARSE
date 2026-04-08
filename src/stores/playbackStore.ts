import { create } from "zustand";

interface PlaybackStore {
  activeSpeaker: string | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  zoom: number;
  playbackRate: number;
  selectedRegion: { start: number; end: number } | null;
  loopEnabled: boolean;

  setActiveSpeaker: (speaker: string) => void;
  setCurrentTime: (t: number) => void;
  setDuration: (d: number) => void;
  setZoom: (z: number) => void;
  setPlaybackRate: (r: number) => void;
  setSelectedRegion: (r: { start: number; end: number } | null) => void;
  toggleLoop: () => void;
  togglePlay: () => void;
}

export const usePlaybackStore = create<PlaybackStore>()((set) => ({
  activeSpeaker: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  zoom: 100,
  playbackRate: 1.0,
  selectedRegion: null,
  loopEnabled: false,

  setActiveSpeaker: (speaker) => set({ activeSpeaker: speaker, currentTime: 0 }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setDuration: (d) => set({ duration: d }),
  setZoom: (z) => set({ zoom: z }),
  setPlaybackRate: (r) => set({ playbackRate: r }),
  setSelectedRegion: (r) => set({ selectedRegion: r }),
  toggleLoop: () => set((s) => ({ loopEnabled: !s.loopEnabled })),
  // togglePlay is controlled externally by useWaveSurfer — this just syncs state
  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),
}));

// Re-export type for consumers
export type { PlaybackStore };
