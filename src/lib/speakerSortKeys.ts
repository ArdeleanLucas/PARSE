import type { AnnotationRecord } from "../api/types";

export type ConceptKeyMap = ReadonlyMap<string, number>;

export interface SpeakerSortKeys {
  byStart: ConceptKeyMap;
  byImportIndex: ConceptKeyMap;
}

export function buildSpeakerSortKeys(record: AnnotationRecord | undefined | null): SpeakerSortKeys {
  const byStart = new Map<string, number>();
  const byImportIndex = new Map<string, number>();
  const intervals = record?.tiers?.concept?.intervals ?? [];

  for (const interval of intervals) {
    const conceptId = interval.concept_id == null ? "" : String(interval.concept_id).trim();
    if (!conceptId) continue;
    if (typeof interval.start === "number" && Number.isFinite(interval.start)) {
      const previous = byStart.get(conceptId);
      if (previous === undefined || interval.start < previous) byStart.set(conceptId, interval.start);
    }
    if (typeof interval.import_index === "number" && Number.isFinite(interval.import_index)) {
      const previous = byImportIndex.get(conceptId);
      if (previous === undefined || interval.import_index < previous) byImportIndex.set(conceptId, interval.import_index);
    }
  }

  return { byStart, byImportIndex };
}
