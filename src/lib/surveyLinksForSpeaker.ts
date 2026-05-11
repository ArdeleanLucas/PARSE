import type { ConceptSurveyLinks, ConceptSurveyLinksByConcept, SpeakerConceptSurveyLinks } from "../api/types";
import { normalizeSurveyId } from "./surveyOverlap";

export interface SpeakerSurveyLinkBucket {
  surveyId: string;
  sourceItem: string;
  rowIds: string[];
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
