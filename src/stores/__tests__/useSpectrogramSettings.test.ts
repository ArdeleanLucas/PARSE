// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import {
  PRAAT_DEFAULTS,
  useSpectrogramSettings,
} from "../useSpectrogramSettings";

describe("useSpectrogramSettings", () => {
  beforeEach(() => {
    localStorage.clear();
    useSpectrogramSettings.setState({ ...PRAAT_DEFAULTS });
  });

  it("initial state matches PRAAT_DEFAULTS", () => {
    const s = useSpectrogramSettings.getState();
    expect(s.windowLengthSec).toBe(PRAAT_DEFAULTS.windowLengthSec);
    expect(s.windowShape).toBe(PRAAT_DEFAULTS.windowShape);
    expect(s.maxFrequencyHz).toBe(PRAAT_DEFAULTS.maxFrequencyHz);
    expect(s.dynamicRangeDb).toBe(PRAAT_DEFAULTS.dynamicRangeDb);
    expect(s.preEmphasisHz).toBe(PRAAT_DEFAULTS.preEmphasisHz);
    expect(s.colorScheme).toBe(PRAAT_DEFAULTS.colorScheme);
  });

  it("set() mutates only the specified key", () => {
    useSpectrogramSettings.getState().set("windowLengthSec", 0.029);
    const after = useSpectrogramSettings.getState();
    expect(after.windowLengthSec).toBe(0.029);
    expect(after.windowShape).toBe(PRAAT_DEFAULTS.windowShape);
    expect(after.maxFrequencyHz).toBe(PRAAT_DEFAULTS.maxFrequencyHz);
    expect(after.dynamicRangeDb).toBe(PRAAT_DEFAULTS.dynamicRangeDb);
    expect(after.preEmphasisHz).toBe(PRAAT_DEFAULTS.preEmphasisHz);
    expect(after.colorScheme).toBe(PRAAT_DEFAULTS.colorScheme);
  });

  it("resetDefaults() restores all six fields", () => {
    const s = useSpectrogramSettings.getState();
    s.set("windowLengthSec", 0.029);
    s.set("colorScheme", "viridis");
    s.set("preEmphasisHz", 0);
    expect(useSpectrogramSettings.getState().windowLengthSec).toBe(0.029);

    useSpectrogramSettings.getState().resetDefaults();
    const after = useSpectrogramSettings.getState();
    expect(after.windowLengthSec).toBe(PRAAT_DEFAULTS.windowLengthSec);
    expect(after.windowShape).toBe(PRAAT_DEFAULTS.windowShape);
    expect(after.maxFrequencyHz).toBe(PRAAT_DEFAULTS.maxFrequencyHz);
    expect(after.dynamicRangeDb).toBe(PRAAT_DEFAULTS.dynamicRangeDb);
    expect(after.preEmphasisHz).toBe(PRAAT_DEFAULTS.preEmphasisHz);
    expect(after.colorScheme).toBe(PRAAT_DEFAULTS.colorScheme);
  });

  it("persists to localStorage under the parse-spectrogram-settings key", () => {
    useSpectrogramSettings.getState().set("colorScheme", "viridis");
    const stored = localStorage.getItem("parse-spectrogram-settings");
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored as string);
    expect(parsed.state.colorScheme).toBe("viridis");
  });
});
