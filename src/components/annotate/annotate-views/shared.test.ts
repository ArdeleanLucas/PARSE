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

function makeFail01HeadRecord(): AnnotationRecord {
  return {
    speaker: "Fail01",
    source_wav: "Fail01.wav",
    tiers: {
      concept: {
        name: "concept",
        display_order: 1,
        intervals: [
          { start: 727.487, end: 728.211, text: "head", concept_id: "247" },
          { start: 731.934, end: 732.612, text: "head", concept_id: "247" },
          { start: 731.95, end: 732.705, text: "head", concept_id: "247" },
        ],
      },
      ipa: {
        name: "ipa",
        display_order: 2,
        intervals: [
          { start: 727.487, end: 728.211, text: "sar" },
          { start: 731.934, end: 732.612, text: "kapul-b" },
          { start: 731.95, end: 732.705, text: "kapul-c" },
        ],
      },
      ortho: {
        name: "ortho",
        display_order: 3,
        intervals: [
          { start: 727.487, end: 728.211, text: "سەر" },
          { start: 731.934, end: 732.612, text: "کەپووڵ ب" },
          { start: 731.95, end: 732.705, text: "کەپووڵ ج" },
        ],
      },
    },
  } as AnnotationRecord;
}

const fail01HeadConcept = { id: 247, key: "247", name: "head" };

describe("annotation concept lookup", () => {
  it("defaults to the first matching realization interval", () => {
    const lookup = findAnnotationForConcept(makeFail01HeadRecord(), fail01HeadConcept);

    expect(lookup.conceptInterval?.start).toBe(727.487);
    expect(lookup.ipaInterval?.text).toBe("sar");
    expect(lookup.orthoInterval?.text).toBe("سەر");
  });

  it("focusedIntervalIndex 0 returns the same realization as the default lookup", () => {
    const record = makeFail01HeadRecord();
    const defaultLookup = findAnnotationForConcept(record, fail01HeadConcept);
    const focusedLookup = findAnnotationForConcept(record, fail01HeadConcept, { focusedIntervalIndex: 0 });

    expect(focusedLookup.conceptInterval?.start).toBe(defaultLookup.conceptInterval?.start);
    expect(focusedLookup.ipaInterval?.text).toBe("sar");
  });

  it("focusedIntervalIndex 1 pivots the lookup to realization B", () => {
    const lookup = findAnnotationForConcept(makeFail01HeadRecord(), fail01HeadConcept, { focusedIntervalIndex: 1 });

    expect(lookup.conceptInterval?.start).toBe(731.934);
    expect(lookup.ipaInterval?.text).toBe("kapul-b");
    expect(lookup.orthoInterval?.text).toBe("کەپووڵ ب");
  });

  it("focusedIntervalIndex 2 pivots the lookup to realization C", () => {
    const lookup = findAnnotationForConcept(makeFail01HeadRecord(), fail01HeadConcept, { focusedIntervalIndex: 2 });

    expect(lookup.conceptInterval?.start).toBe(731.95);
    expect(lookup.ipaInterval?.text).toBe("kapul-c");
  });

  it("falls back to the first interval when focusedIntervalIndex is out of range", () => {
    const lookup = findAnnotationForConcept(makeFail01HeadRecord(), fail01HeadConcept, { focusedIntervalIndex: 99 });

    expect(lookup.conceptInterval?.start).toBe(727.487);
    expect(lookup.ipaInterval?.text).toBe("sar");
  });
  it("returns no concept interval when matching concept lacks concept_id on every candidate row", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 100, end: 110, text: "ten" },
      { start: 200, end: 210, text: "to listen to" },
    ]);

    const lookup = findAnnotationForConcept(record, { id: 226, key: "226", name: "ten" });

    expect(lookup.conceptInterval).toBeNull();
  });

  it("matches the cid-bearing row even when an earlier text fallback would have matched before", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 100, end: 110, text: "to listen to" },
      { start: 200, end: 210, text: "ten", concept_id: "226", import_index: 144 } as AnnotationRecord["tiers"][string]["intervals"][number],
    ]);

    const lookup = findAnnotationForConcept(record, { id: 226, key: "226", name: "ten" });

    expect(lookup.conceptInterval?.start).toBe(200);
  });


  it("uses the raw concept key instead of the grouped display id for shifted grouped rows", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 4013.131, end: 4013.999, text: "big", concept_id: "53" },
      { start: 5090.250, end: 5091.125, text: "long", concept_id: "55" },
    ]);

    const lookup = findAnnotationForConcept(record, {
      id: 53,
      key: "55",
      name: "long",
      variants: [{ conceptKey: "55", conceptEn: "long", variantLabel: "A" }],
    });

    expect(lookup.conceptInterval).toMatchObject({ start: 5090.250, end: 5091.125, text: "long", concept_id: "55" });
  });

  it("does not let a grouped source_item key collide with an earlier master concept_id", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 2259.36, end: 2260.119, text: "dog", concept_id: "298", audition_prefix: "79" },
      { start: 3001.5, end: 3002.25, text: "this", concept_id: "547", audition_prefix: "298" },
    ]);

    const lookup = findAnnotationForConcept(record, {
      id: 3,
      key: "298",
      name: "this",
      variants: [
        { conceptKey: "504", conceptEn: "this (A)", variantLabel: "A" },
        { conceptKey: "505", conceptEn: "this (B)", variantLabel: "B" },
        { conceptKey: "547", conceptEn: "this", variantLabel: "C" },
      ],
    });

    expect(lookup.conceptInterval).toMatchObject({ start: 3001.5, end: 3002.25, text: "this", concept_id: "547" });
  });

  it("matches the grouped variant master id when the colliding singleton row appears later", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 3001.5, end: 3002.25, text: "this", concept_id: "547", audition_prefix: "298" },
      { start: 2259.36, end: 2260.119, text: "dog", concept_id: "298", audition_prefix: "79" },
    ]);

    const lookup = findAnnotationForConcept(record, {
      id: 3,
      key: "298",
      name: "this",
      variants: [
        { conceptKey: "504", conceptEn: "this (A)", variantLabel: "A" },
        { conceptKey: "505", conceptEn: "this (B)", variantLabel: "B" },
        { conceptKey: "547", conceptEn: "this", variantLabel: "C" },
      ],
    });

    expect(lookup.conceptInterval).toMatchObject({ start: 3001.5, end: 3002.25, text: "this", concept_id: "547" });
  });

  it("keeps display ortho_words separate from strict ortho-tier annotation status", () => {
    const record = makeRecordWithConceptIntervals([
      { start: 100, end: 110, text: "one", concept_id: "217" },
    ]);
    record.tiers.ortho_words = {
      name: "ortho_words",
      display_order: 4,
      intervals: [{ start: 100, end: 110, text: "one", concept_id: "217" }],
    };

    const lookup = findAnnotationForConcept(record, { id: 217, key: "217", name: "one" });

    expect(lookup.orthoInterval?.text).toBe("one");
    expect(lookup.directOrthoInterval).toBeNull();
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
