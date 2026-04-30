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
  it("prefers the later explicit concept-id interval over an earlier short-name substring collision", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 10091.681, end: 10092.674, text: "to listen to" },
      { start: 1219.304, end: 1219.835, text: "ten", concept_id: "226", import_index: 144 } as AnnotationRecord["tiers"][string]["intervals"][number],
    ]);

    const lookup = findAnnotationForConcept(record, { id: 226, key: "JBIL_10.A", name: "ten" });

    expect(lookup.conceptInterval?.start).toBe(1219.304);
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
