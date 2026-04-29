import { create } from "zustand";

interface PlaybackStore {
  activeSpeaker: string | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  zoom: number;
  playbackRate: number;
  volume: number;
  selectedRegion: { start: number; end: number } | null;
  loopEnabled: boolean;
  // Cross-component seek signal. Components outside AnnotateView (e.g. the
  // right-panel "Search & anchor" block) call requestSeek(); AnnotateView
  // watches `pendingSeek.nonce` and drives its wavesurfer instance.
  pendingSeek: { targetSec: number; nonce: number } | null;

  setActiveSpeaker: (speaker: string) => void;
  setCurrentTime: (t: number) => void;
  setDuration: (d: number) => void;
  setZoom: (z: number) => void;
  setPlaybackRate: (r: number) => void;
  setVolume: (v: number) => void;
  setSelectedRegion: (r: { start: number; end: number } | null) => void;
  toggleLoop: () => void;
  togglePlay: () => void;
  requestSeek: (targetSec: number) => void;
}

export const usePlaybackStore = create<PlaybackStore>()((set) => ({
  activeSpeaker: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  zoom: 100,
  playbackRate: 1.0,
  volume: 0.8,
  selectedRegion: null,
  loopEnabled: false,
  pendingSeek: null,

  setActiveSpeaker: (speaker) => set({ activeSpeaker: speaker, currentTime: 0 }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setDuration: (d) => set({ duration: d }),
  setZoom: (z) => set({ zoom: z }),
  setPlaybackRate: (r) => set({ playbackRate: r }),
  setVolume: (v) => set({ volume: Math.max(0, Math.min(1, v)) }),
  setSelectedRegion: (r) => set({ selectedRegion: r }),
  toggleLoop: () => set((s) => ({ loopEnabled: !s.loopEnabled })),
  // togglePlay is controlled externally by useWaveSurfer — this just syncs state
  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),
  requestSeek: (targetSec) => set((s) => ({
    pendingSeek: { targetSec, nonce: (s.pendingSeek?.nonce ?? 0) + 1 },
  })),
}));

// Re-export type for consumers
export type { PlaybackStore };
