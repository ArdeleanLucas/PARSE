import { describe, expect, it } from "vitest";
import type { AnnotationRecord } from "../api/types";
import {
  applyAddInterval,
  applyMergeIntervals,
  applySetInterval,
  applySplitInterval,
  applyUpdateIntervalTimes,
} from "./annotationStoreIntervals";

function seedRecord(): AnnotationRecord {
  return {
    speaker: "S1",
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 2,
        intervals: [
          { start: 0, end: 1, text: "a" },
          { start: 1, end: 2, text: "b" },
        ],
      },
      ortho: {
        name: "ortho",
        display_order: 3,
        intervals: [{ start: 0, end: 1, text: "هه‌ر" }],
      },
    },
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    source_wav: "x.wav",
  };
}

describe("annotationStoreIntervals", () => {
  it("setInterval replaces a matching interval and preserves sorted order", () => {
    const next = applySetInterval(seedRecord(), "ipa", {
      start: 0,
      end: 1,
      text: "A",
    });
    expect(next).not.toBeNull();
    expect(next!.tiers.ipa.intervals.map((i) => i.text)).toEqual(["A", "b"]);
  });

  it("addInterval creates missing tiers using canonical order and sorts by start", () => {
    const next = applyAddInterval(seedRecord(), "stt", {
      start: 4,
      end: 5,
      text: "seg",
    });
    expect(next).not.toBeNull();
    expect(next!.tiers.stt.display_order).toBe(5);
    expect(next!.tiers.stt.intervals[0].text).toBe("seg");
  });

  it("updateIntervalTimes flags the retimed interval as manuallyAdjusted", () => {
    const next = applyUpdateIntervalTimes(seedRecord(), "ipa", 0, 0.1, 0.9);
    expect(next).not.toBeNull();
    expect(next!.tiers.ipa.intervals[0]).toMatchObject({
      start: 0.1,
      end: 0.9,
      manuallyAdjusted: true,
    });
  });

  it("mergeIntervals joins adjacent text and splitInterval creates an empty right half", () => {
    const merged = applyMergeIntervals(seedRecord(), "ipa", 0);
    expect(merged).not.toBeNull();
    expect(merged!.tiers.ipa.intervals[0]).toMatchObject({
      start: 0,
      end: 2,
      text: "a b",
      manuallyAdjusted: true,
    });

    const split = applySplitInterval(merged!, "ipa", 0, 0.75);
    expect(split).not.toBeNull();
    expect(split!.tiers.ipa.intervals[0]).toMatchObject({ end: 0.75, text: "a b" });
    expect(split!.tiers.ipa.intervals[1]).toMatchObject({ start: 0.75, end: 2, text: "" });
  });
});
