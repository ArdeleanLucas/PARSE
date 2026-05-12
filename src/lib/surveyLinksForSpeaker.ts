import type { ConceptSurveyLinks, ConceptSurveyLinksByConcept, SpeakerConceptSurveyLinks } from "../api/types";
import { normalizeSurveyId } from "./surveyOverlap";

export interface SpeakerSurveyLinkBucket {
  surveyId: string;
  sourceItem: string;
  rowIds: string[];
}

interface SurveyConceptKeyCarrier {
  key?: string | null;
  mergedKeys?: readonly (string | null | undefined)[] | null;
  variants?: readonly { conceptKey?: string | null }[] | null;
  mergedVariants?: readonly { conceptKey?: string | null }[] | null;
}

function normalizedRowId(value: string | null | undefined): string {
  return String(value ?? "").trim();
}

export function surveyRowIdsForConcept(concept: SurveyConceptKeyCarrier): string[] {
  const ids = new Set<string>();
  const add = (value: string | null | undefined) => {
    const id = normalizedRowId(value);
    if (id) ids.add(id);
  };

  for (const variant of concept.variants ?? []) add(variant.conceptKey);
  for (const key of concept.mergedKeys ?? []) add(key);
  for (const variant of concept.mergedVariants ?? []) add(variant.conceptKey);
  if (ids.size === 0) add(concept.key);
  return [...ids];
}

function normalizeLinks(links: ConceptSurveyLinks | undefined): ConceptSurveyLinks {
  const normalized: ConceptSurveyLinks = {};
  for (const [surveyId, sourceItem] of Object.entries(links ?? {})) {
    const key = normalizeSurveyId(surveyId);
    const item = String(sourceItem ?? "").trim();
    if (key && item) normalized[key] = item;
  }
  return normalized;
}

export function resolveSurveyLinksForSpeaker(
  rowIds: readonly string[],
  speaker: string | null | undefined,
  globalLinks: ConceptSurveyLinksByConcept | undefined,
  speakerOverrides: SpeakerConceptSurveyLinks | undefined,
): SpeakerSurveyLinkBucket[] {
  const buckets = new Map<string, SpeakerSurveyLinkBucket>();
  const activeSpeakerOverrides = speaker ? speakerOverrides?.[speaker] : undefined;

  for (const rawRowId of rowIds) {
    const rowId = String(rawRowId ?? "").trim();
    if (!rowId) continue;
    const overrideLinks = normalizeLinks(activeSpeakerOverrides?.[rowId]);
    const hasOverride = Object.keys(overrideLinks).length > 0;
    const links = hasOverride ? overrideLinks : normalizeLinks(globalLinks?.[rowId]);
    for (const [surveyId, sourceItem] of Object.entries(links)) {
      const key = `${surveyId}\u0000${sourceItem}`;
      const bucket = buckets.get(key) ?? { surveyId, sourceItem, rowIds: [] };
      bucket.rowIds.push(rowId);
      buckets.set(key, bucket);
    }
  }

  return [...buckets.values()]
    .map((bucket) => ({ ...bucket, rowIds: [...bucket.rowIds].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })) }))
    .sort((a, b) => a.surveyId.localeCompare(b.surveyId) || a.sourceItem.localeCompare(b.sourceItem, undefined, { numeric: true }));
}
