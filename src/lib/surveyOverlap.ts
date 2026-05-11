import type {
  ConceptSurveyLinks,
  ConceptSurveyLinksByConcept,
  SpeakerSurveyChoices,
  SurveyDisplaySettings,
  SurveySettingsMap,
} from "../api/types";
import type { Concept } from "./speakerForm";

const DEFAULT_DISPLAY_COLOR = "slate";

export const SURVEY_CHIP_CLASSES: Record<string, string> = {
  indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200',
  sky: 'bg-sky-50 text-sky-700 ring-sky-200',
  teal: 'bg-teal-50 text-teal-700 ring-teal-200',
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  orange: 'bg-orange-50 text-orange-700 ring-orange-200',
  rose: 'bg-rose-50 text-rose-700 ring-rose-200',
  pink: 'bg-pink-50 text-pink-700 ring-pink-200',
  slate: 'bg-slate-100 text-slate-600 ring-slate-200',
};

export const SURVEY_BADGE_TEXT_CLASSES: Record<string, string> = {
  indigo: 'text-indigo-500',
  violet: 'text-violet-500',
  blue: 'text-blue-500',
  sky: 'text-sky-500',
  teal: 'text-teal-500',
  emerald: 'text-emerald-500',
  amber: 'text-amber-500',
  orange: 'text-orange-500',
  rose: 'text-rose-500',
  pink: 'text-pink-500',
  slate: 'text-slate-400',
};

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

export function aggregateWorkspaceSurveys(
  concepts: readonly Concept[] | undefined,
  settings: SurveySettingsMap | undefined,
  links: ConceptSurveyLinksByConcept | undefined = undefined,
): string[] {
  const surveyIds = new Set<string>();

  for (const surveyId of Object.keys(settings ?? {})) {
    const normalized = normalizeSurveyId(surveyId);
    if (normalized) surveyIds.add(normalized);
  }

  for (const conceptLinks of Object.values(links ?? {})) {
    for (const surveyId of Object.keys(conceptLinks ?? {})) {
      const normalized = normalizeSurveyId(surveyId);
      if (normalized) surveyIds.add(normalized);
    }
  }

  for (const concept of concepts ?? []) {
    for (const surveyId of Object.keys(surveyLinksForConcept(concept))) {
      const normalized = normalizeSurveyId(surveyId);
      if (normalized) surveyIds.add(normalized);
    }
  }

  return [...surveyIds].sort();
}
