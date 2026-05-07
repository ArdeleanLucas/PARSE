import { describe, expect, it } from "vitest";
import type { Concept } from "./speakerForm";
import {
  compareConceptsByResolvedSurvey,
  defaultSurveySettings,
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

  it("sorts by each speaker's resolved survey item with missing items last", () => {
    const rain = makeConcept({ id: 1, key: "rain", name: "rain", sourceItem: "KLQ_1.10", surveys: { klq: "KLQ_1.10", jbil: "JBIL_100" } });
    const fire = makeConcept({ id: 2, key: "fire", name: "fire", sourceItem: "KLQ_2.1", surveys: { klq: "KLQ_2.1", jbil: "JBIL_2" } });
    const unknown = makeConcept({ id: 3, key: "unknown", name: "unknown", sourceItem: undefined, sourceSurvey: undefined, surveys: undefined });

    const choices = { Saha01: { rain: "jbil", fire: "jbil" } };

    expect([fire, rain, unknown].sort((a, b) => compareConceptsByResolvedSurvey(a, b, "Fail01", {}, {})).map((c) => c.key)).toEqual([
      "rain",
      "fire",
      "unknown",
    ]);
    expect([rain, fire, unknown].sort((a, b) => compareConceptsByResolvedSurvey(a, b, "Saha01", choices, {})).map((c) => c.key)).toEqual([
      "fire",
      "rain",
      "unknown",
    ]);
  });
});
