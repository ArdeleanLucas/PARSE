import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { SpectrogramParams } from "../workers/spectrogram-worker";

export const PRAAT_DEFAULTS: SpectrogramParams = {
  windowLengthSec: 0.005,
  windowShape: "gaussian",
  maxFrequencyHz: 5500,
  dynamicRangeDb: 50,
  preEmphasisHz: 50,
  colorScheme: "praat",
};

interface SettingsStore extends SpectrogramParams {
  set: <K extends keyof SpectrogramParams>(key: K, value: SpectrogramParams[K]) => void;
  resetDefaults: () => void;
}

export const useSpectrogramSettings = create<SettingsStore>()(
  persist(
    (setState) => ({
      ...PRAAT_DEFAULTS,
      set: (key, value) => setState({ [key]: value } as Partial<SettingsStore>),
      resetDefaults: () => setState({ ...PRAAT_DEFAULTS }),
    }),
    { name: "parse-spectrogram-settings" },
  ),
);
