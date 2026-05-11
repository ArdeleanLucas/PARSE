import { describe, expect, it } from "vitest";
import type { AnnotationRecord } from "../api/types";
import { buildSpeakerSortKeys } from "./speakerSortKeys";

function recordWithConcepts(intervals: Array<{ concept_id?: string; start: number; import_index?: number }>): AnnotationRecord {
  return {
    speaker: "Qasr01",
    tiers: {
      concept: {
        name: "concept",
        display_order: 1,
        intervals: intervals.map((interval, index) => ({
          start: interval.start,
          end: interval.start + 0.5,
          text: `concept-${index}`,
          concept_id: interval.concept_id,
          import_index: interval.import_index,
        })),
      },
    },
  };
}

describe("buildSpeakerSortKeys", () => {
  it("keeps earliest start and lowest import_index per concept id", () => {
    const keys = buildSpeakerSortKeys(recordWithConcepts([
      { concept_id: "1", start: 5, import_index: 3 },
      { concept_id: "2", start: 0.5, import_index: 0 },
      { concept_id: "1", start: 4, import_index: 7 },
      { concept_id: "3", start: 12, import_index: 1 },
      { concept_id: "4", start: 2, import_index: 2 },
      { start: 1, import_index: 99 },
    ]));

    expect([...keys.byStart.entries()]).toEqual([
      ["1", 4],
      ["2", 0.5],
      ["3", 12],
      ["4", 2],
    ]);
    expect([...keys.byImportIndex.entries()]).toEqual([
      ["1", 3],
      ["2", 0],
      ["3", 1],
      ["4", 2],
    ]);
  });
});
