import { describe, expect, it } from "vitest";
import type { Concept } from "./speakerForm";
import {
  aggregateWorkspaceSurveys,
  defaultSurveySettings,
  normalizeDisplayColor,
  normalizeSurveyId,
  resolveConceptSurvey,
  surveyLabelFor,
} from "./surveyOverlap";

const makeConcept = (overrides: Partial<Concept> = {}): Concept => ({
  id: 1,
  key: "rain",
  name: "rain",
  tag: "untagged",
  sourceItem: "KLQ_1.10",
  sourceSurvey: "KLQ",
  surveys: { klq: "KLQ_1.10", jbil: "JBIL_100" },
  ...overrides,
});

describe("survey-overlap frontend helpers", () => {
  it("normalizes survey ids with the backend sidecar rules", () => {
    expect(normalizeSurveyId("  JBIL Survey!! ")).toBe("jbil_survey");
    expect(normalizeSurveyId("KLQ")).toBe("klq");
    expect(normalizeSurveyId(null)).toBe("");
  });

  it("normalizes legacy indigo display color to violet while preserving other values", () => {
    expect(normalizeDisplayColor("indigo")).toBe("violet");
    for (const color of ["violet", "emerald", "amber", "rose", "slate", "teal", "blue", "fuchsia"]) {
      expect(normalizeDisplayColor(color)).toBe(color);
    }
    expect(normalizeDisplayColor("")).toBe("");
    expect(normalizeDisplayColor(null)).toBe("");
    expect(normalizeDisplayColor(undefined)).toBe("");
  });

  it("supplies display defaults without enabling color semantics", () => {
    expect(defaultSurveySettings("klq")).toEqual({ display_label: "KLQ", display_color: "slate" });
    expect(surveyLabelFor("jbil", {})).toBe("JBIL");
    expect(surveyLabelFor("klq", { klq: { display_label: "Kurdish List", display_color: "teal" } })).toBe("Kurdish List");
  });

  it("resolves a speaker's chosen survey before falling back to the canonical CSV survey", () => {
    const resolved = resolveConceptSurvey(makeConcept(), "Saha01", {
      Saha01: { rain: "jbil" },
    }, {
      jbil: { display_label: "JBIL", display_color: "blue" },
    });

    expect(resolved).toMatchObject({
      conceptKey: "rain",
      surveyId: "jbil",
      sourceItem: "JBIL_100",
      displayLabel: "JBIL",
      displayColor: "blue",
      hasOverlap: true,
    });

    const fallback = resolveConceptSurvey(makeConcept(), "Fail01", {}, {});
    expect(fallback).toMatchObject({ surveyId: "klq", sourceItem: "KLQ_1.10", displayLabel: "KLQ", hasOverlap: true });
  });

  it("keeps legacy single-survey concepts readable without a sidecar", () => {
    const resolved = resolveConceptSurvey(
      makeConcept({ surveys: undefined, sourceItem: "2.15", sourceSurvey: "KLQ" }),
      "Fail01",
      { Fail01: { rain: "jbil" } },
      {},
    );

    expect(resolved).toMatchObject({ surveyId: "klq", sourceItem: "2.15", hasOverlap: false });
  });

  it("aggregates workspace survey ids from settings, sidecar links, and legacy concept fields", () => {
    const concepts = [
      makeConcept({ key: "rain", surveys: { klq: "KLQ_1.10" }, sourceSurvey: "KLQ" }),
      makeConcept({ key: "fire", surveys: { jbil: "JBIL_2" }, sourceSurvey: undefined }),
      makeConcept({ key: "stone", surveys: undefined, sourceSurvey: "SSWL", sourceItem: "sswl-9" }),
    ];

    expect(aggregateWorkspaceSurveys(concepts, { wals: { display_label: "WALS", display_color: "blue" } }, {
      wind: { abvd: "ABVD-1" },
      water: { klq: "KLQ_2" },
    })).toEqual(["abvd", "jbil", "klq", "sswl", "wals"]);
  });

});
