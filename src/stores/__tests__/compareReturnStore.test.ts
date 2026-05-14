import { describe, it, expect, beforeEach } from "vitest";

import {
  useCompareReturnStore,
  type CompareReturnSnapshot,
} from "../compareReturnStore";

const SAMPLE: CompareReturnSnapshot = {
  conceptId: 17,
  conceptKey: "concept-17-key",
  expandedSpeaker: "SPK_03",
};

describe("compareReturnStore", () => {
  beforeEach(() => {
    useCompareReturnStore.getState().clear();
  });

  it("starts with a null snapshot", () => {
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });

  it("save() stores the snapshot exactly as given", () => {
    useCompareReturnStore.getState().save(SAMPLE);
    expect(useCompareReturnStore.getState().snapshot).toEqual(SAMPLE);
  });

  it("consume() returns the saved snapshot and clears it", () => {
    useCompareReturnStore.getState().save(SAMPLE);
    const consumed = useCompareReturnStore.getState().consume();
    expect(consumed).toEqual(SAMPLE);
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });

  it("consume() returns null when no snapshot is buffered", () => {
    expect(useCompareReturnStore.getState().consume()).toBeNull();
  });

  it("a second consume() without an intervening save returns null", () => {
    useCompareReturnStore.getState().save(SAMPLE);
    expect(useCompareReturnStore.getState().consume()).toEqual(SAMPLE);
    expect(useCompareReturnStore.getState().consume()).toBeNull();
  });

  it("save() overwrites a previously buffered snapshot", () => {
    useCompareReturnStore.getState().save(SAMPLE);
    const next: CompareReturnSnapshot = {
      conceptId: 42,
      conceptKey: "concept-42",
      expandedSpeaker: "SPK_07",
    };
    useCompareReturnStore.getState().save(next);
    expect(useCompareReturnStore.getState().snapshot).toEqual(next);
  });

  it("clear() resets snapshot to null", () => {
    useCompareReturnStore.getState().save(SAMPLE);
    useCompareReturnStore.getState().clear();
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });

  it("clear() on an empty store is a no-op", () => {
    expect(() => useCompareReturnStore.getState().clear()).not.toThrow();
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });
});
