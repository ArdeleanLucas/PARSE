// Empirical reproduction of the concept-list sort bug:
// a grouped concept whose `concept.key` is a bare source_item string (e.g. "298")
// collides in the sort-key Map with a real concept_id of the same value.
// For Fail01: "this JBIL 298" (key="298") collides with concept_id 298 = "dog (A)",
// so the "this" row ends up using dog's interval time as its sort key, placing it
// between dog and horn in the rendered concept list instead of at its true position
// far later (Fail01's actual "this" interval is at 5732s).

import { describe, expect, it } from "vitest";
import type { AnnotationRecord } from "../api/types";
import { buildSpeakerSortKeys } from "./speakerSortKeys";
import { conceptUnderlyingKeys } from "./speakerElicitedConcepts";

interface TestConcept {
  key: string;
  name: string;
  variants?: ReadonlyArray<{ conceptKey: string }>;
}

const dogConcept: TestConcept = {
  key: "79",
  name: "dog",
  variants: [
    { conceptKey: "298" },
    { conceptKey: "628" },
    { conceptKey: "636" },
  ],
};

const thisConcept: TestConcept = {
  key: "298", // source_item for JBIL 298 — collides with dog's concept_id 298
  name: "this",
  variants: [
    { conceptKey: "504" },
    { conceptKey: "505" },
    { conceptKey: "547" },
  ],
};

const hornConcept: TestConcept = {
  key: "81",
  name: "horn (cow)",
  variants: [{ conceptKey: "300" }],
};

function buildFail01Record(): AnnotationRecord {
  return {
    speaker: "Fail01",
    source_audio: "Fail01.wav",
    source_audio_duration_sec: 9999,
    metadata: { created: "", modified: "" },
    tiers: {
      concept: {
        intervals: [
          { start: 1560.057, end: 1560.772, text: "dog", concept_id: "636" },
          { start: 1560.870, end: 1561.690, text: "dog (A)", concept_id: "298" },
          { start: 1590.204, end: 1590.948, text: "horn (cow)", concept_id: "300" },
          { start: 5732.991, end: 5733.885, text: "this", concept_id: "547" },
          { start: 5738.097, end: 5738.785, text: "this", concept_id: "547" },
        ],
      },
    },
  } as unknown as AnnotationRecord;
}

function makeValueForConcept(
  keys: ReadonlyMap<string, number>,
  underlyingKeysOf: (c: TestConcept) => string[],
): (c: TestConcept) => number | undefined {
  return (candidate) => {
    let best: number | undefined;
    for (const key of underlyingKeysOf(candidate)) {
      const value = keys.get(key);
      if (value !== undefined && (best === undefined || value < best)) best = value;
    }
    return best;
  };
}

describe("concept sort key collision (regression test for source_item↔concept_id collision)", () => {
  it("'this JBIL 298' sorts at its actual interval time (5732s), not at the colliding dog (A) interval (1560s)", () => {
    const record = buildFail01Record();
    const { byStart } = buildSpeakerSortKeys(record);
    const valueFor = makeValueForConcept(byStart, conceptUnderlyingKeys);

    const dogKey = valueFor(dogConcept);
    const thisKey = valueFor(thisConcept);
    const hornKey = valueFor(hornConcept);

    expect(dogKey).toBeCloseTo(1560.057, 3);
    expect(hornKey).toBeCloseTo(1590.204, 3);
    expect(thisKey).toBeCloseTo(5732.991, 3);
    expect(thisKey).toBeGreaterThan(hornKey ?? 0);
  });

  it("singleton concepts (no variants) still resolve via concept.key — the fix only excludes concept.key for grouped rows", () => {
    const record = buildFail01Record();
    const { byStart } = buildSpeakerSortKeys(record);
    const valueFor = makeValueForConcept(byStart, conceptUnderlyingKeys);

    const singletonHorn: TestConcept = { key: "300", name: "horn (cow)" };
    expect(valueFor(singletonHorn)).toBeCloseTo(1590.204, 3);
  });

  it("mergedKeys and mergedVariants are still consulted even when concept.key is excluded", () => {
    const record = buildFail01Record();
    const { byStart } = buildSpeakerSortKeys(record);
    const valueFor = makeValueForConcept(byStart, conceptUnderlyingKeys);

    const merged = {
      key: "999",
      name: "merged",
      variants: [{ conceptKey: "999" }],
      mergedVariants: [{ conceptKey: "300" }],
    };
    expect(valueFor(merged)).toBeCloseTo(1590.204, 3);
  });
});
