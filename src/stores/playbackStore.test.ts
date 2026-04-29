import { describe, it, expect, beforeEach } from "vitest";

import { usePlaybackStore } from "./playbackStore";

// Captured before any test runs so it reflects the store's documented default,
// not a value mutated by a sibling test.
const INITIAL_VOLUME = usePlaybackStore.getState().volume;

describe("playbackStore.volume default", () => {
  it("defaults to 0.8 at module-load time", () => {
    expect(INITIAL_VOLUME).toBe(0.8);
  });
});

describe("playbackStore.setVolume clamping", () => {
  beforeEach(() => {
    usePlaybackStore.setState({ volume: 0.8 });
  });

  it("clamps negative input to 0", () => {
    usePlaybackStore.getState().setVolume(-1);
    expect(usePlaybackStore.getState().volume).toBe(0);
  });

  it("clamps input above 1 to 1", () => {
    usePlaybackStore.getState().setVolume(2);
    expect(usePlaybackStore.getState().volume).toBe(1);
  });

  it("passes values within [0, 1] through unchanged", () => {
    usePlaybackStore.getState().setVolume(0);
    expect(usePlaybackStore.getState().volume).toBe(0);
    usePlaybackStore.getState().setVolume(0.5);
    expect(usePlaybackStore.getState().volume).toBe(0.5);
    usePlaybackStore.getState().setVolume(1);
    expect(usePlaybackStore.getState().volume).toBe(1);
  });
});
