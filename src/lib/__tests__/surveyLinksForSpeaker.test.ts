import { describe, expect, it } from "vitest";
import { resolveSurveyLinksForSpeaker } from "../surveyLinksForSpeaker";

const globalLinks = {
  "53": { klq: "4.1" },
  "619": { KLQ: "4.1" },
  "150": { jbil: "169" },
};

const speakerOverrides = {
  Saha01: {
    "53": { jbil: "169" },
    "619": { jbil: "169" },
  },
  Fail01: {
    "53": { klq: "4.2" },
  },
};

describe("resolveSurveyLinksForSpeaker", () => {
  it("returns an empty list for empty row ids", () => {
    expect(resolveSurveyLinksForSpeaker([], "Saha01", globalLinks, speakerOverrides)).toEqual([]);
  });

  it("falls back to global links when no speaker override exists", () => {
    expect(resolveSurveyLinksForSpeaker(["53"], "Mand01", globalLinks, speakerOverrides)).toEqual([
      { surveyId: "klq", sourceItem: "4.1", rowIds: ["53"] },
    ]);
  });

  it("uses speaker overrides before global links", () => {
    expect(resolveSurveyLinksForSpeaker(["53"], "Saha01", globalLinks, speakerOverrides)).toEqual([
      { surveyId: "jbil", sourceItem: "169", rowIds: ["53"] },
    ]);
  });

  it("keeps overrides from different speakers isolated", () => {
    expect(resolveSurveyLinksForSpeaker(["53"], "Fail01", globalLinks, speakerOverrides)).toEqual([
      { surveyId: "klq", sourceItem: "4.2", rowIds: ["53"] },
    ]);
  });

  it("collapses multiple row ids into one shared bucket", () => {
    expect(resolveSurveyLinksForSpeaker(["619", "53"], "Saha01", globalLinks, speakerOverrides)).toEqual([
      { surveyId: "jbil", sourceItem: "169", rowIds: ["53", "619"] },
    ]);
  });

  it("keeps distinct survey/source pairs in separate deterministic buckets", () => {
    expect(resolveSurveyLinksForSpeaker(["150", "53"], "Mand01", globalLinks, speakerOverrides)).toEqual([
      { surveyId: "jbil", sourceItem: "169", rowIds: ["150"] },
      { surveyId: "klq", sourceItem: "4.1", rowIds: ["53"] },
    ]);
  });

  it("normalizes survey ids and trims source items", () => {
    expect(resolveSurveyLinksForSpeaker(["1"], null, { "1": { " KLQ ": " 4.1 " } }, {})).toEqual([
      { surveyId: "klq", sourceItem: "4.1", rowIds: ["1"] },
    ]);
  });

  it("ignores blank row ids and blank link values", () => {
    expect(resolveSurveyLinksForSpeaker(["", "2"], "Saha01", { "2": { klq: "" } }, {})).toEqual([]);
  });
});
