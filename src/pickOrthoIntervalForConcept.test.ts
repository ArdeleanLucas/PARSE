import { describe, it, expect } from "vitest";
import type { AnnotationRecord, AnnotationInterval } from "./api/types";
import { pickOrthoIntervalForConcept } from "./ParseUI";

function makeRecord(partial: {
  ortho?: AnnotationInterval[];
  ortho_words?: AnnotationInterval[];
}): AnnotationRecord {
  return {
    speaker: "Fail02",
    tiers: {
      ipa_phone: { name: "ipa_phone", display_order: 1, intervals: [] },
      ipa:       { name: "ipa",       display_order: 2, intervals: [] },
      ortho:     { name: "ortho",     display_order: 3, intervals: partial.ortho ?? [] },
      ortho_words: { name: "ortho_words", display_order: 4, intervals: partial.ortho_words ?? [] },
      stt:       { name: "stt",       display_order: 5, intervals: [] },
      concept:   { name: "concept",   display_order: 6, intervals: [] },
      sentence:  { name: "sentence",  display_order: 7, intervals: [] },
      speaker:   { name: "speaker",   display_order: 8, intervals: [] },
    },
    source_wav: "",
  };
}

describe("pickOrthoIntervalForConcept", () => {
  const conceptInterval: AnnotationInterval = { start: 10.0, end: 10.4, text: "hair" };

  it("prefers the word-level tier over the coarse ortho tier", () => {
    const record = makeRecord({
      ortho: [{ start: 0, end: 300, text: "whole narrative dumped here" }],
      ortho_words: [
        { start: 5.0, end: 5.3, text: "other" },
        { start: 10.1, end: 10.3, text: "مووی" },
      ],
    });

    const picked = pickOrthoIntervalForConcept(record, conceptInterval);
    expect(picked?.text).toBe("مووی");
  });

  it("falls back to the coarse ortho tier when ortho_words is empty", () => {
    const record = makeRecord({
      ortho: [{ start: 10.0, end: 10.4, text: "مووی" }],
      ortho_words: [],
    });
    expect(pickOrthoIntervalForConcept(record, conceptInterval)?.text).toBe("مووی");
  });

  it("picks the word with the greatest overlap when none is strictly contained", () => {
    const record = makeRecord({
      ortho_words: [
        { start: 9.8, end: 10.15, text: "left" },   // 0.15s overlap
        { start: 10.25, end: 10.6, text: "right" }, // 0.15s overlap — same, first wins
        { start: 10.0, end: 10.3, text: "center" }, // 0.30s overlap — best
      ],
    });
    expect(pickOrthoIntervalForConcept(record, conceptInterval)?.text).toBe("center");
  });

  it("returns null when no tier has a matching interval", () => {
    const record = makeRecord({});
    expect(pickOrthoIntervalForConcept(record, conceptInterval)).toBeNull();
  });
});
