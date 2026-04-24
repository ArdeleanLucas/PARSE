import { describe, it, expect } from "vitest";
import type { AnnotationRecord } from "../api/types";
import {
  levenshtein,
  normalizedLevenshtein,
  normalizeForMatch,
  searchLexeme,
} from "./lexemeSearch";

function tier(
  intervals: Array<{ start: number; end: number; text: string }>,
  name: string,
  display_order: number,
) {
  return { name, display_order, intervals };
}

function recordWith(
  tiers: Record<string, { name: string; display_order: number; intervals: Array<{ start: number; end: number; text: string }> }>,
): AnnotationRecord {
  return {
    speaker: "TestSpeaker",
    tiers,
  };
}

describe("levenshtein", () => {
  it("reports 0 for equal strings", () => {
    expect(levenshtein("yek", "yek")).toBe(0);
  });
  it("reports single-char distance", () => {
    expect(levenshtein("yek", "jek")).toBe(1);
    expect(levenshtein("yek", "yak")).toBe(1);
  });
  it("reports insertion/deletion cost", () => {
    expect(levenshtein("yek", "yeke")).toBe(1);
    expect(levenshtein("abc", "")).toBe(3);
  });
});

describe("normalizedLevenshtein", () => {
  it("returns 0 for identical", () => {
    expect(normalizedLevenshtein("abc", "abc")).toBe(0);
  });
  it("scales by longer length", () => {
    expect(normalizedLevenshtein("yek", "yak")).toBeCloseTo(1 / 3);
    expect(normalizedLevenshtein("yek", "yakyak")).toBeCloseTo(4 / 6);
  });
});

describe("normalizeForMatch", () => {
  it("strips punctuation and lowercases", () => {
    expect(normalizeForMatch("Yek!")).toBe("yek");
    expect(normalizeForMatch("  YEK-e  ")).toBe("yeke");
  });
  it("collapses whitespace", () => {
    expect(normalizeForMatch("yek   du")).toBe("yek du");
  });
});

describe("searchLexeme", () => {
  it("returns no candidates when record is null", () => {
    expect(searchLexeme(null, ["yek"])).toEqual([]);
  });

  it("returns no candidates for empty variants", () => {
    const r = recordWith({
      ortho: tier([{ start: 0, end: 1, text: "yek" }], "ortho", 3),
    });
    expect(searchLexeme(r, [])).toEqual([]);
  });

  it("finds an exact orth match", () => {
    const r = recordWith({
      ortho: tier(
        [
          { start: 0, end: 0.5, text: "yek" },
          { start: 1, end: 1.4, text: "du" },
        ],
        "ortho",
        3,
      ),
    });
    const hits = searchLexeme(r, ["yek"]);
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].matchedText).toBe("yek");
    expect(hits[0].tier).toBe("ortho");
    expect(hits[0].score).toBeGreaterThan(0.8);
  });

  it("prefers ortho_words over ortho for the same text", () => {
    const r = recordWith({
      ortho_words: tier([{ start: 0, end: 0.5, text: "yek" }], "ortho_words", 4),
      ortho: tier([{ start: 0.05, end: 0.55, text: "yek" }], "ortho", 3),
    });
    const hits = searchLexeme(r, ["yek"]);
    // Both tiers matched at near-identical ranges → dedup wins the higher
    // tier. ortho_words has the greater weight.
    expect(hits[0].tier).toBe("ortho_words");
  });

  it("catches near-misses within distance threshold", () => {
    const r = recordWith({
      ortho: tier([{ start: 0, end: 0.5, text: "jek" }], "ortho", 3),
    });
    const hits = searchLexeme(r, ["yek"]);
    expect(hits.length).toBe(1);
    expect(hits[0].matchedVariant).toBe("yek");
  });

  it("merges adjacent short intervals so split words are caught", () => {
    const r = recordWith({
      ortho_words: tier(
        [
          { start: 0.1, end: 0.22, text: "ye" },
          { start: 0.24, end: 0.35, text: "k" },
        ],
        "ortho_words",
        4,
      ),
    });
    const hits = searchLexeme(r, ["yek"]);
    // Should match the MERGED interval spanning both halves.
    const merged = hits.find((h) => h.start < 0.15 && h.end > 0.3);
    expect(merged).toBeDefined();
    expect(merged!.matchedText).toBe("ye k");
  });

  it("respects the maxNormalizedDistance threshold", () => {
    const r = recordWith({
      ortho: tier([{ start: 0, end: 0.5, text: "totally different" }], "ortho", 3),
    });
    expect(searchLexeme(r, ["yek"])).toEqual([]);
  });

  it("limits results", () => {
    const intervals = Array.from({ length: 20 }, (_, i) => ({
      start: i,
      end: i + 0.3,
      text: "yek",
    }));
    const r = recordWith({
      ortho: tier(intervals, "ortho", 3),
    });
    expect(searchLexeme(r, ["yek"], { limit: 5 })).toHaveLength(5);
  });

  it("token-matches so a variant hits the first word of a multi-word segment", () => {
    const r = recordWith({
      ortho: tier([{ start: 5, end: 6, text: "yek dînarê" }], "ortho", 3),
    });
    const hits = searchLexeme(r, ["yek"]);
    expect(hits.length).toBe(1);
  });
});
