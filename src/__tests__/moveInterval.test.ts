import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("../api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: vi.fn(),
  saveAnnotation: vi.fn(),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  getAnnotation: vi.fn(),
  saveAnnotation: vi.fn(),
}));

import { useAnnotationStore } from "../stores/annotationStore";
import { LEXEME_SCOPE_TIERS } from "../stores/annotation/actions";

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
    histories: {},
  });
}

function seedFail02AllTiers() {
  useAnnotationStore.setState({
    records: {
      Fail02: {
        speaker: "Fail02",
        tiers: {
          ipa_phone: {
            name: "ipa_phone", display_order: 0,
            intervals: [{ start: 100, end: 101, text: "h ɪ r" }],
          },
          ipa: {
            name: "ipa", display_order: 1,
            intervals: [{ start: 100, end: 101, text: "hɪr" }],
          },
          ortho: {
            name: "ortho", display_order: 2,
            intervals: [{ start: 100, end: 101, text: "هەر" }],
          },
          ortho_words: {
            name: "ortho_words", display_order: 3,
            intervals: [{ start: 100, end: 101, text: "هەر" }],
          },
          stt: {
            name: "stt", display_order: 4,
            intervals: [{ start: 100, end: 101, text: "har" }],
          },
          concept: {
            name: "concept", display_order: 5,
            intervals: [{ start: 100, end: 101, text: "hair" }],
          },
          sentence: {
            name: "sentence", display_order: 6,
            intervals: [{ start: 100, end: 101, text: "sentence" }],
          },
          speaker: {
            name: "speaker", display_order: 7,
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
    histories: {},
  });
}

function seedFail02RealShape() {
  // Real-world: ipa/ortho/ortho_words have their own boundaries from
  // independent STT/forced-alignment passes that do not coincide with the
  // concept span. This mirrors real PARSE annotation files.
  useAnnotationStore.setState({
    records: {
      Fail02: {
        speaker: "Fail02",
        tiers: {
          ipa: {
            name: "ipa", display_order: 1,
            intervals: [
              { start: 99.50, end: 99.95, text: "prev" },
              { start: 99.95, end: 101.10, text: "hɪr" },
              { start: 101.20, end: 101.50, text: "next" },
            ],
          },
          ortho: {
            name: "ortho", display_order: 2,
            intervals: [{ start: 99.90, end: 101.05, text: "هەر" }],
          },
          ortho_words: {
            name: "ortho_words", display_order: 3,
            intervals: [
              { start: 99.90, end: 100.50, text: "" },
              { start: 100.50, end: 101.05, text: "" },
              { start: 101.20, end: 101.50, text: "" },
            ],
          },
          concept: {
            name: "concept", display_order: 4,
            intervals: [{ start: 100.000, end: 101.000, text: "hair" }],
          },
          speaker: {
            name: "speaker", display_order: 5,
            intervals: [{ start: 0, end: 200, text: "Fail02" }],
          },
        },
        created_at: "2026-01-01T00:00:00Z",
        modified_at: "2026-01-01T00:00:00Z",
        source_wav: "x.wav",
      },
    },
    dirty: {}, loading: {}, histories: {},
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

  it("retains the generic full-tier walk when tierScope is omitted", () => {
    seedFail02AllTiers();
    const moved = useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Fail02", 100, 101, 200, 201,
    );
    expect(moved).toBe(8);
    const rec = useAnnotationStore.getState().records["Fail02"];
    for (const tierName of ["ipa_phone", "ipa", "ortho", "ortho_words", "stt", "concept", "sentence", "speaker"]) {
      expect(rec.tiers[tierName].intervals[0]).toMatchObject({ start: 200, end: 201, manuallyAdjusted: true });
    }
  });

  it("with LEXEME_SCOPE_TIERS, only retimes concept/ipa/ortho/ortho_words", () => {
    seedFail02AllTiers();
    const moved = useAnnotationStore.getState().moveIntervalAcrossTiers(
      "Fail02", 100, 101, 200, 201, LEXEME_SCOPE_TIERS,
    );
    expect(moved).toBe(4);

    const rec = useAnnotationStore.getState().records["Fail02"];
    for (const tierName of ["concept", "ipa", "ortho", "ortho_words"]) {
      expect(rec.tiers[tierName].intervals[0]).toMatchObject({ start: 200, end: 201, manuallyAdjusted: true });
    }
    for (const tierName of ["stt", "sentence", "speaker", "ipa_phone"]) {
      expect(rec.tiers[tierName].intervals[0]).toMatchObject({ start: 100, end: 101 });
      expect(rec.tiers[tierName].intervals[0].manuallyAdjusted).toBeFalsy();
    }
  });
});

describe("annotationStore.saveLexemeAnnotation", () => {
  beforeEach(() => {
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {}, histories: {} });
  });

  it("commits one undoable mutation for retime + text edits across the 4 lexeme tiers", () => {
    seedFail02AllTiers();
    const result = useAnnotationStore.getState().saveLexemeAnnotation({
      speaker: "Fail02",
      oldStart: 100,
      oldEnd: 101,
      newStart: 200,
      newEnd: 201,
      ipaText: "new-ipa",
      orthoText: "نوێ",
      conceptName: "new-concept",
    });

    expect(result).toEqual({ ok: true, moved: 4 });

    const state = useAnnotationStore.getState();
    const rec = state.records["Fail02"];
    expect(rec.tiers.ipa.intervals[0]).toMatchObject({ start: 200, end: 201, text: "new-ipa", manuallyAdjusted: true });
    expect(rec.tiers.ortho.intervals[0]).toMatchObject({ start: 200, end: 201, text: "نوێ", manuallyAdjusted: true });
    expect(rec.tiers.concept.intervals[0]).toMatchObject({ start: 200, end: 201, text: "new-concept", manuallyAdjusted: true });
    expect(rec.tiers.ortho_words.intervals[0]).toMatchObject({ start: 200, end: 201, text: "هەر", manuallyAdjusted: true });
    expect(rec.tiers.stt.intervals[0]).toMatchObject({ start: 100, end: 101, text: "har" });
    expect(rec.tiers.sentence.intervals[0]).toMatchObject({ start: 100, end: 101, text: "sentence" });
    expect(rec.tiers.speaker.intervals[0]).toMatchObject({ start: 100, end: 101, text: "Fail02" });
    expect(rec.tiers.ipa_phone.intervals[0]).toMatchObject({ start: 100, end: 101, text: "h ɪ r" });

    const history = state.histories["Fail02"];
    expect(history.undo).toHaveLength(1);
    expect(history.undo[0].label).toBe("save lexeme annotation");

    const undoLabel = state.undo("Fail02");
    expect(undoLabel).toBe("save lexeme annotation");

    const undone = useAnnotationStore.getState().records["Fail02"];
    expect(undone.tiers.ipa.intervals[0]).toMatchObject({ start: 100, end: 101, text: "hɪr" });
    expect(undone.tiers.ortho.intervals[0]).toMatchObject({ start: 100, end: 101, text: "هەر" });
    expect(undone.tiers.concept.intervals[0]).toMatchObject({ start: 100, end: 101, text: "hair" });
    expect(undone.tiers.ortho_words.intervals[0]).toMatchObject({ start: 100, end: 101, text: "هەر" });
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


describe("annotationStore.saveLexemeAnnotation (real-shape data)", () => {
  beforeEach(() => {
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {}, histories: {} });
  });

  it("retimes IPA/ORTH by overlap and scales ortho_words by midpoint when bounds differ from concept", () => {
    seedFail02RealShape();
    const result = useAnnotationStore.getState().saveLexemeAnnotation({
      speaker: "Fail02",
      oldStart: 100, oldEnd: 101,
      newStart: 200, newEnd: 202,
      ipaText: "ndʒə",
      orthoText: "نوێ",
      conceptName: "hair",
    });
    expect(result).toEqual({ ok: true, moved: 4 });

    const rec = useAnnotationStore.getState().records["Fail02"];

    expect(rec.tiers.concept.intervals[0]).toMatchObject({
      start: 200, end: 202, text: "hair", manuallyAdjusted: true,
    });

    const movedIpa = rec.tiers.ipa.intervals.find((iv) => iv.text === "ndʒə");
    expect(movedIpa).toMatchObject({ start: 200, end: 202, manuallyAdjusted: true });
    expect(rec.tiers.ipa.intervals.find((iv) => iv.text === "prev")).toMatchObject({ start: 99.50, end: 99.95 });
    expect(rec.tiers.ipa.intervals.find((iv) => iv.text === "next")).toMatchObject({ start: 101.20, end: 101.50 });

    expect(rec.tiers.ortho.intervals[0]).toMatchObject({
      start: 200, end: 202, text: "نوێ", manuallyAdjusted: true,
    });

    const words = [...rec.tiers.ortho_words.intervals].sort((a, b) => a.start - b.start);
    expect(words).toHaveLength(3);
    expect(words[0]).toMatchObject({ start: 101.20, end: 101.50 });
    expect(words[0].manuallyAdjusted).toBeFalsy();
    expect(words[1].start).toBeCloseTo(200);
    expect(words[1].end).toBeCloseTo(201);
    expect(words[1].manuallyAdjusted).toBe(true);
    expect(words[2].start).toBeCloseTo(201);
    expect(words[2].end).toBeCloseTo(202);
    expect(words[2].manuallyAdjusted).toBe(true);
  });

  it("returns moved=0 with a clean error when no concept interval matches", () => {
    seedFail02RealShape();
    const result = useAnnotationStore.getState().saveLexemeAnnotation({
      speaker: "Fail02",
      oldStart: 500, oldEnd: 501,
      newStart: 600, newEnd: 601,
      ipaText: "x", orthoText: "y", conceptName: "z",
    });
    expect(result).toEqual({ ok: false, error: "No matching lexeme intervals found." });
  });
});
