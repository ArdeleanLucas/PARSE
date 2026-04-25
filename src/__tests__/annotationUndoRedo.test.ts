import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: vi.fn(),
  saveAnnotation: vi.fn().mockResolvedValue(undefined),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
}));

import { useAnnotationStore } from "../stores/annotationStore";
import type { AnnotationRecord } from "../api/types";

function seed(): AnnotationRecord {
  return {
    speaker: "S1",
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 2,
        intervals: [
          { start: 0, end: 1, text: "a" },
          { start: 1, end: 2, text: "b" },
          { start: 2, end: 3, text: "c" },
        ],
      },
      stt: { name: "stt", display_order: 5, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    source_wav: "x.wav",
  };
}

describe("annotationStore undo/redo", () => {
  beforeEach(() => {
    useAnnotationStore.setState({
      records: { S1: seed() },
      dirty: { S1: false },
      loading: {},
      histories: {},
    });
  });

  it("undo restores pre-merge state after merge-with-next", () => {
    const store = useAnnotationStore.getState();
    store.mergeIntervals("S1", "ipa", 0);

    const merged = useAnnotationStore.getState().records.S1.tiers.ipa.intervals;
    expect(merged).toHaveLength(2);
    // Merges flag the resulting interval as manuallyAdjusted so a future
    // partial re-run preserves the user's grouping decision.
    expect(merged[0]).toEqual({
      start: 0,
      end: 2,
      text: "a b",
      manuallyAdjusted: true,
    });

    const label = useAnnotationStore.getState().undo("S1");
    // Label flows into the "Undid X" toast — pin the exact human text so a
    // future "improvement" that reverts to raw slugs gets caught.
    expect(label).toBe("merge with next (IPA)");

    const restored = useAnnotationStore.getState().records.S1.tiers.ipa.intervals;
    expect(restored).toHaveLength(3);
    expect(restored.map((i) => i.text)).toEqual(["a", "b", "c"]);
  });

  it("redo re-applies the merge after an undo", () => {
    const store = useAnnotationStore.getState();
    store.mergeIntervals("S1", "ipa", 1);
    useAnnotationStore.getState().undo("S1");
    useAnnotationStore.getState().redo("S1");

    const ivs = useAnnotationStore.getState().records.S1.tiers.ipa.intervals;
    expect(ivs).toHaveLength(2);
    expect(ivs[1]).toEqual({
      start: 1,
      end: 3,
      text: "b c",
      manuallyAdjusted: true,
    });
  });

  it("updateInterval / undo swaps text back", () => {
    useAnnotationStore.getState().updateInterval("S1", "ipa", 0, "X");
    expect(useAnnotationStore.getState().records.S1.tiers.ipa.intervals[0].text).toBe("X");
    useAnnotationStore.getState().undo("S1");
    expect(useAnnotationStore.getState().records.S1.tiers.ipa.intervals[0].text).toBe("a");
  });

  it("new mutation clears the redo stack", () => {
    useAnnotationStore.getState().updateInterval("S1", "ipa", 0, "X");
    useAnnotationStore.getState().undo("S1");
    expect(useAnnotationStore.getState().histories.S1.redo).toHaveLength(1);
    useAnnotationStore.getState().updateInterval("S1", "ipa", 0, "Y");
    expect(useAnnotationStore.getState().histories.S1.redo).toHaveLength(0);
  });

  it("history caps at 50 entries per speaker", () => {
    for (let i = 0; i < 60; i += 1) {
      useAnnotationStore.getState().updateInterval("S1", "ipa", 0, `t${i}`);
    }
    expect(useAnnotationStore.getState().histories.S1.undo).toHaveLength(50);
  });

  it("undo returns null when stack is empty", () => {
    expect(useAnnotationStore.getState().undo("S1")).toBeNull();
  });

  it("labels use human tier names, not raw slugs", () => {
    const store = useAnnotationStore.getState();
    store.updateInterval("S1", "ipa", 0, "X");
    expect(useAnnotationStore.getState().undo("S1")).toBe("text edit (IPA)");

    store.splitInterval("S1", "ipa", 0, 0.5);
    expect(useAnnotationStore.getState().undo("S1")).toBe("split (IPA)");

    store.removeInterval("S1", "ipa", 0);
    expect(useAnnotationStore.getState().undo("S1")).toBe("delete IPA segment");

    store.addInterval("S1", "ipa", { start: 10, end: 11, text: "z" });
    expect(useAnnotationStore.getState().undo("S1")).toBe("add IPA segment");

    store.updateIntervalTimes("S1", "ipa", 0, 0.1, 0.9);
    expect(useAnnotationStore.getState().undo("S1")).toBe("retime IPA segment");
  });

  it("setConfirmedAnchor label distinguishes confirm vs clear", () => {
    const store = useAnnotationStore.getState();
    store.setConfirmedAnchor("S1", "c1", { start: 0, end: 1 });
    expect(useAnnotationStore.getState().histories.S1.undo.slice(-1)[0]?.label).toBe(
      "confirm concept anchor",
    );
    store.setConfirmedAnchor("S1", "c1", null);
    expect(useAnnotationStore.getState().histories.S1.undo.slice(-1)[0]?.label).toBe(
      "clear concept anchor",
    );
  });

  it("ensureSttTier copies segments and is idempotent", () => {
    const segs = [
      { start: 0, end: 1, text: "one" },
      { start: 1, end: 2, text: "two" },
    ];
    useAnnotationStore.getState().ensureSttTier("S1", segs);
    let stt = useAnnotationStore.getState().records.S1.tiers.stt.intervals;
    expect(stt).toEqual(segs);

    // Second call must not re-migrate or push another history entry.
    const histLenBefore = useAnnotationStore.getState().histories.S1.undo.length;
    useAnnotationStore.getState().ensureSttTier("S1", [
      { start: 5, end: 6, text: "nope" },
    ]);
    stt = useAnnotationStore.getState().records.S1.tiers.stt.intervals;
    expect(stt).toEqual(segs);
    expect(useAnnotationStore.getState().histories.S1.undo).toHaveLength(histLenBefore);
  });

  it("undo after ensureSttTier restores the empty-tier state", () => {
    useAnnotationStore.getState().ensureSttTier("S1", [
      { start: 0, end: 1, text: "one" },
    ]);
    useAnnotationStore.getState().undo("S1");
    expect(useAnnotationStore.getState().records.S1.tiers.stt.intervals).toHaveLength(0);
  });
});
