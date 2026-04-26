import { describe, expect, it } from "vitest";

import { createAnnotationActionsSlice } from "./actions";
import { createAnnotationPersistenceSlice } from "./persistence";
import {
  countProtectedConceptLexemes,
  selectSpeakerDirty,
  selectSpeakerLoading,
  selectSpeakerRecord,
} from "./selectors";

describe("annotation store extracted slices", () => {
  it("exports slice factories for actions and persistence", () => {
    expect(typeof createAnnotationActionsSlice).toBe("function");
    expect(typeof createAnnotationPersistenceSlice).toBe("function");
  });

  it("selectors expose stable derived lookups for one speaker", () => {
    const state = {
      records: {
        S1: {
          speaker: "S1",
          tiers: {
            concept: {
              name: "concept",
              display_order: 1,
              intervals: [
                { start: 0, end: 1, text: "water", manuallyAdjusted: true },
                { start: 1, end: 2, text: "fire" },
              ],
            },
          },
          created_at: "2026-01-01T00:00:00Z",
          modified_at: "2026-01-01T00:00:00Z",
          source_wav: "S1.wav",
        },
      },
      dirty: { S1: true },
      loading: { S1: false },
    };

    expect(selectSpeakerRecord(state, "S1")?.speaker).toBe("S1");
    expect(selectSpeakerDirty(state, "S1")).toBe(true);
    expect(selectSpeakerLoading(state, "S1")).toBe(false);
    expect(countProtectedConceptLexemes(state, "S1")).toBe(1);
    expect(countProtectedConceptLexemes(state, "ghost")).toBe(0);
  });
});
