import type {
  ConceptSurveyLinks,
  SpeakerSurveyChoices,
  SurveyDisplaySettings,
  SurveySettingsMap,
} from "../api/types";
import type { Concept } from "./speakerForm";
import { compareSurveyKeys } from "./surveySort";

const DEFAULT_DISPLAY_COLOR = "slate";

export interface ResolvedConceptSurvey {
  conceptKey: string;
  surveyId: string;
  sourceItem: string;
  displayLabel: string;
  displayColor: string;
  hasOverlap: boolean;
  availableSurveys: ConceptSurveyLinks;
}

export function normalizeSurveyId(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_.-]/g, "");
}

export function defaultSurveySettings(surveyId: string): SurveyDisplaySettings {
  const normalized = normalizeSurveyId(surveyId);
  return {
    display_label: normalized ? normalized.toLocaleUpperCase() : "",
    display_color: DEFAULT_DISPLAY_COLOR,
  };
}

export function surveyLabelFor(surveyId: string, settings: SurveySettingsMap | undefined): string {
  const normalized = normalizeSurveyId(surveyId);
  const configured = settings?.[normalized]?.display_label?.trim();
  return configured || defaultSurveySettings(normalized).display_label;
}

function surveyColorFor(surveyId: string, settings: SurveySettingsMap | undefined): string {
  const normalized = normalizeSurveyId(surveyId);
  return settings?.[normalized]?.display_color?.trim() || DEFAULT_DISPLAY_COLOR;
}

function conceptChoiceKeys(concept: Concept): string[] {
  if (concept.mergedKeys?.length) return [...concept.mergedKeys];
  if (concept.variants?.length) return concept.variants.map((variant) => variant.conceptKey);
  return [concept.key];
}

export function surveyChoiceKeysForConcept(concept: Concept): string[] {
  return Object.keys(surveyLinksForConcept(concept)).sort();
}

export function surveyLinksForConcept(concept: Concept): ConceptSurveyLinks {
  const links: ConceptSurveyLinks = {};
  for (const [surveyId, sourceItem] of Object.entries(concept.surveys ?? {})) {
    const normalized = normalizeSurveyId(surveyId);
    const item = String(sourceItem ?? "").trim();
    if (normalized && item) links[normalized] = item;
  }
  if (Object.keys(links).length > 0) return links;

  const legacySurvey = normalizeSurveyId(concept.sourceSurvey);
  const legacyItem = concept.sourceItem?.trim();
  if (legacySurvey && legacyItem) links[legacySurvey] = legacyItem;
  return links;
}

function speakerChoiceForConcept(
  concept: Concept,
  speaker: string | null | undefined,
  choices: SpeakerSurveyChoices | undefined,
  links: ConceptSurveyLinks,
): string {
  const speakerChoices = speaker ? choices?.[speaker] : undefined;
  if (!speakerChoices) return "";
  for (const choiceKey of conceptChoiceKeys(concept)) {
    const normalized = normalizeSurveyId(speakerChoices[choiceKey]);
    if (normalized && Object.prototype.hasOwnProperty.call(links, normalized)) return normalized;
  }
  return "";
}

export function resolveConceptSurvey(
  concept: Concept,
  speaker: string | null | undefined,
  choices: SpeakerSurveyChoices | undefined,
  settings: SurveySettingsMap | undefined,
): ResolvedConceptSurvey {
  const links = surveyLinksForConcept(concept);
  const surveyIds = Object.keys(links).sort();
  const chosen = speakerChoiceForConcept(concept, speaker, choices, links);
  const legacy = normalizeSurveyId(concept.sourceSurvey);
  const fallback = legacy && Object.prototype.hasOwnProperty.call(links, legacy) ? legacy : surveyIds[0] ?? "";
  const surveyId = chosen || fallback;
  const sourceItem = surveyId ? links[surveyId] ?? "" : "";

  return {
    conceptKey: concept.key,
    surveyId,
    sourceItem,
    displayLabel: surveyLabelFor(surveyId, settings),
    displayColor: surveyColorFor(surveyId, settings),
    hasOverlap: surveyIds.length > 1,
    availableSurveys: links,
  };
}

export function compareConceptsByResolvedSurvey(
  left: Concept,
  right: Concept,
  speaker: string | null | undefined,
  choices: SpeakerSurveyChoices | undefined,
  settings: SurveySettingsMap | undefined,
): number {
  const leftResolved = resolveConceptSurvey(left, speaker, choices, settings);
  const rightResolved = resolveConceptSurvey(right, speaker, choices, settings);
  const leftMissing = !leftResolved.sourceItem;
  const rightMissing = !rightResolved.sourceItem;
  if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
  const bySurveyItem = compareSurveyKeys(leftResolved.sourceItem, rightResolved.sourceItem);
  if (bySurveyItem !== 0) return bySurveyItem;
  return left.name.localeCompare(right.name, undefined, { sensitivity: "base" });
}
