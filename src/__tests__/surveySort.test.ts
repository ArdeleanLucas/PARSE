import { describe, it, expect } from "vitest";
import { compareSurveyKeys, surveyBadgePrefix, surveyKey } from "../lib/surveySort";

// Regression guard for the concept sidebar's Survey sort. PR #113 introduced
// the natural-sort behavior; PR #114 accidentally reverted it because the
// previous test suite had its own copy of `surveyKey`. Both the production
// sort and the badge prefix now import from `src/lib/surveySort.ts`, so any
// future branch that reverts those helpers will fail these cases.

describe("survey-item natural sort", () => {
  it("tokenises survey_item into letter-runs and integer-runs", () => {
    expect(surveyKey("KLQ_1.10.A")).toEqual(["klq", 1, 10, "a"]);
    expect(surveyKey("JBIL_100.A")).toEqual(["jbil", 100, "a"]);
  });

  it("orders JBIL numerically: 1, 2, 10, 11, 100 (not 1, 10, 100, 11, 2)", () => {
    const items = ["JBIL_10.A", "JBIL_100.A", "JBIL_11.A", "JBIL_1.A", "JBIL_2.A"];
    const sorted = [...items].sort(compareSurveyKeys);
    expect(sorted).toEqual([
      "JBIL_1.A", "JBIL_2.A", "JBIL_10.A", "JBIL_11.A", "JBIL_100.A",
    ]);
  });

  it("treats KLQ section.item as two integers (not a decimal)", () => {
    // The pre-fix regex captured 1.10 as a float (1.1), so KLQ_1.10.A would
    // land *before* KLQ_1.2.A. Guard that explicitly.
    const items = [
      "KLQ_1.10.A", "KLQ_1.2.A", "KLQ_1.2.B", "KLQ_2.1.A", "KLQ_1.1.A",
    ];
    const sorted = [...items].sort(compareSurveyKeys);
    expect(sorted).toEqual([
      "KLQ_1.1.A", "KLQ_1.2.A", "KLQ_1.2.B", "KLQ_1.10.A", "KLQ_2.1.A",
    ]);
  });

  it("groups by source prefix before number (JBIL before KLQ alphabetically)", () => {
    const items = ["KLQ_1.1.A", "JBIL_1.A", "KLQ_2.1.A", "JBIL_10.A"];
    const sorted = [...items].sort(compareSurveyKeys);
    expect(sorted).toEqual([
      "JBIL_1.A", "JBIL_10.A", "KLQ_1.1.A", "KLQ_2.1.A",
    ]);
  });

  it("A/B variants on the same (section,item) stay adjacent in variant order", () => {
    const items = ["KLQ_1.2.B", "KLQ_1.1.A", "KLQ_1.2.A"];
    const sorted = [...items].sort(compareSurveyKeys);
    expect(sorted).toEqual(["KLQ_1.1.A", "KLQ_1.2.A", "KLQ_1.2.B"]);
  });

  it("unprefixed numeric survey ids sort numerically too", () => {
    // Fallback for workspaces that store bare numeric ids.
    const items = ["10", "100", "11", "1", "2"];
    const sorted = [...items].sort(compareSurveyKeys);
    expect(sorted).toEqual(["1", "2", "10", "11", "100"]);
  });
});

describe("survey-mode badge prefix", () => {
  it("emits no extra letter in Survey mode — survey_item carries its own source tag", () => {
    // This is the half of the regression that slipped past the old tests.
    // Specifically blocks re-introducing the "Q" prefix seen in the
    // user-reported regression where the sidebar read "QJBIL_1.A" instead
    // of "JBIL_1.A".
    expect(surveyBadgePrefix("survey")).toBe("");
    expect(surveyBadgePrefix("survey")).not.toBe("Q");
  });

  it("uses # for numeric-id sort modes", () => {
    expect(surveyBadgePrefix("1n")).toBe("#");
    expect(surveyBadgePrefix("az")).toBe("#");
    expect(surveyBadgePrefix("")).toBe("#");
  });
});
