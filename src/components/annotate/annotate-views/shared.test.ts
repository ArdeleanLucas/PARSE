import { describe, expect, it } from "vitest";

import type { AnnotationRecord } from "../../../api/types";
import { findAnnotationForConcept, formatPlaybackTime, formatPlayhead } from "./shared";

function makeRecordWithConceptIntervals(intervals: AnnotationRecord["tiers"][string]["intervals"]): AnnotationRecord {
  return {
    speaker: "Saha01",
    tiers: {
      concept: { name: "concept", display_order: 1, intervals },
      ipa: { name: "ipa", display_order: 2, intervals: [] },
      ortho: { name: "ortho", display_order: 3, intervals: [] },
    },
    source_wav: "",
  };
}

describe("annotation concept lookup", () => {
  it("returns no concept interval when matching concept lacks concept_id on every candidate row", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 100, end: 110, text: "ten" },
      { start: 200, end: 210, text: "to listen to" },
    ]);

    const lookup = findAnnotationForConcept(record, { id: 226, key: "JBIL_10.A", name: "ten" });

    expect(lookup.conceptInterval).toBeNull();
  });

  it("matches the cid-bearing row even when an earlier text fallback would have matched before", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 100, end: 110, text: "to listen to" },
      { start: 200, end: 210, text: "ten", concept_id: "226", import_index: 144 } as AnnotationRecord["tiers"][string]["intervals"][number],
    ]);

    const lookup = findAnnotationForConcept(record, { id: 226, key: "JBIL_10.A", name: "ten" });

    expect(lookup.conceptInterval?.start).toBe(200);
  });
});

describe("annotate view time formatting", () => {
  it("formats waveform playhead time with two decimals while preserving padding", () => {
    expect(formatPlayhead(0)).toBe("0:00.00");
    expect(formatPlayhead(5.125)).toBe("0:05.13");
    expect(formatPlayhead(65.1)).toBe("1:05.10");
    expect(formatPlayhead(-1)).toBe("0:00.00");
  });

  it("keeps playback timestamps on their existing two-decimal formatter", () => {
    expect(formatPlaybackTime(5.125)).toBe("00:05.12");
  });
});
