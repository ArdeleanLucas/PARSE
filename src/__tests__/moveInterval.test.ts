import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: vi.fn(),
  saveAnnotation: vi.fn(),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
}));

import { useAnnotationStore } from "../stores/annotationStore";

function seedFail02() {
  useAnnotationStore.setState({
    records: {
      Fail02: {
        speaker: "Fail02",
        tiers: {
          ipa: {
            name: "ipa", display_order: 1,
            intervals: [{ start: 100, end: 101, text: "hɪr" }],
          },
          ortho: {
            name: "ortho", display_order: 2,
            intervals: [{ start: 100, end: 101, text: "هەر" }],
          },
          concept: {
            name: "concept", display_order: 3,
            intervals: [{ start: 100, end: 101, text: "hair" }],
          },
          speaker: {
            name: "speaker", display_order: 4,
            intervals: [{ start: 100, end: 101, text: "Fail02" }],
          },
        },
        created_at: "2026-01-01T00:00:00Z",
        modified_at: "2026-01-01T00:00:00Z",
        source_wav: "x.wav",
      },
    },
    dirty: {},
    loading: {},
  });
}

describe("annotationStore.moveIntervalAcrossTiers", () => {
  beforeEach(() => {
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} });
  });

  it("retimes every tier that carries the matching (oldStart,oldEnd) interval and preserves text", () => {
    seedFail02();
    const moved = useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Fail02", 100, 101, 99.5, 101.2,
    );
    expect(moved).toBe(4);

    const rec = useAnnotationStore.getState().records["Fail02"];
    for (const tierName of ["ipa", "ortho", "concept", "speaker"]) {
      const tier = rec.tiers[tierName];
      expect(tier.intervals).toHaveLength(1);
      expect(tier.intervals[0].start).toBeCloseTo(99.5);
      expect(tier.intervals[0].end).toBeCloseTo(101.2);
    }
    expect(rec.tiers.ipa.intervals[0].text).toBe("hɪr");
    expect(rec.tiers.concept.intervals[0].text).toBe("hair");
    expect(useAnnotationStore.getState().dirty["Fail02"]).toBe(true);
  });

  it("returns 0 and leaves records untouched when no matching interval exists", () => {
    seedFail02();
    const moved = useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Fail02", 999, 1000, 1, 2,
    );
    expect(moved).toBe(0);
    const rec = useAnnotationStore.getState().records["Fail02"];
    expect(rec.tiers.ipa.intervals[0].start).toBe(100);
    expect(useAnnotationStore.getState().dirty["Fail02"]).toBeFalsy();
  });

  it("rejects invalid end <= start and non-finite inputs", () => {
    seedFail02();
    expect(
      useAnnotationStore.getState().moveIntervalAcrossTiers("Fail02", 100, 101, 5, 2),
    ).toBe(0);
    expect(
      useAnnotationStore.getState().moveIntervalAcrossTiers("Fail02", 100, 101, NaN, 5),
    ).toBe(0);
    const rec = useAnnotationStore.getState().records["Fail02"];
    expect(rec.tiers.concept.intervals[0].start).toBe(100);
  });

  it("tolerates 1ms timestamp drift when matching", () => {
    seedFail02();
    // Caller passes slightly drifted numbers (floating point round-trip)
    const moved = useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Fail02", 100.0004, 100.9997, 101, 102,
    );
    expect(moved).toBe(4);
    const rec = useAnnotationStore.getState().records["Fail02"];
    expect(rec.tiers.concept.intervals[0].start).toBeCloseTo(101);
  });

  it("returns 0 for unknown speaker", () => {
    const moved = useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Ghost01", 1, 2, 3, 4,
    );
    expect(moved).toBe(0);
  });

  it("flags every moved interval as manuallyAdjusted so future offsets skip it", () => {
    seedFail02();
    useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Fail02", 100, 101, 99.5, 101.2,
    );
    const rec = useAnnotationStore.getState().records["Fail02"];
    for (const tierName of ["ipa", "ortho", "concept", "speaker"]) {
      expect(rec.tiers[tierName].intervals[0].manuallyAdjusted).toBe(true);
    }
  });
});

describe("annotationStore.updateIntervalTimes", () => {
  beforeEach(() => {
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} });
  });

  it("flags the retimed interval as manuallyAdjusted", () => {
    seedFail02();
    useAnnotationStore.getState().updateIntervalTimes("Fail02", "concept", 0, 101, 102);
    const rec = useAnnotationStore.getState().records["Fail02"];
    expect(rec.tiers.concept.intervals[0].manuallyAdjusted).toBe(true);
    expect(rec.tiers.concept.intervals[0].start).toBeCloseTo(101);
    // Untouched tier stays unflagged.
    expect(rec.tiers.ipa.intervals[0].manuallyAdjusted).toBeFalsy();
  });
});

describe("annotationStore.markLexemeManuallyAdjusted", () => {
  beforeEach(() => {
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} });
  });

  it("flags every matching interval across all tiers and marks the record dirty", () => {
    seedFail02();
    const flagged = useAnnotationStore.getState().markLexemeManuallyAdjusted(
      "Fail02", 100, 101,
    );
    expect(flagged).toBe(4);
    const rec = useAnnotationStore.getState().records["Fail02"];
    for (const tierName of ["ipa", "ortho", "concept", "speaker"]) {
      expect(rec.tiers[tierName].intervals[0].manuallyAdjusted).toBe(true);
    }
    expect(useAnnotationStore.getState().dirty["Fail02"]).toBe(true);
  });

  it("tolerates 1ms drift when matching", () => {
    seedFail02();
    const flagged = useAnnotationStore.getState().markLexemeManuallyAdjusted(
      "Fail02", 100.0004, 100.9997,
    );
    expect(flagged).toBe(4);
  });

  it("returns 0 and leaves the record clean when nothing matches", () => {
    seedFail02();
    const flagged = useAnnotationStore.getState().markLexemeManuallyAdjusted(
      "Fail02", 5, 6,
    );
    expect(flagged).toBe(0);
    const rec = useAnnotationStore.getState().records["Fail02"];
    expect(rec.tiers.concept.intervals[0].manuallyAdjusted).toBeFalsy();
    expect(useAnnotationStore.getState().dirty["Fail02"]).toBeFalsy();
  });

  it("returns 0 for unknown speaker", () => {
    expect(
      useAnnotationStore.getState().markLexemeManuallyAdjusted("Ghost01", 1, 2),
    ).toBe(0);
  });
});
