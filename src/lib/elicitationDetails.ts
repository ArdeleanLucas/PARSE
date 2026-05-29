import type { AnnotationInterval, AnnotationRecord } from '../api/types';
import { assignVariantLetters } from './conceptGrouping';

/** One elicitation chip's disambiguating detail: its A/B/C label, the survey
 * source item it came from, and the IPA/ortho transcribed at that interval. */
export interface ElicitationDetail {
  label: string;
  sourceItem: string;
  ipa: string;
  ortho: string;
}

function overlaps(a: AnnotationInterval, b: AnnotationInterval): boolean {
  return a.start < b.end && b.start < a.end;
}

/** Distinct, non-empty texts from `source` intervals overlapping `target`,
 * joined with " / " (e.g. multiple IPA candidates for one recording). */
function textOverlapping(source: readonly AnnotationInterval[], target: AnnotationInterval): string {
  const seen = new Set<string>();
  for (const interval of source) {
    if (!overlaps(interval, target)) continue;
    const text = (interval.text ?? '').trim();
    if (text) seen.add(text);
  }
  return [...seen].join(' / ');
}

/**
 * Build per-concept elicitation detail for one speaker's annotation record.
 *
 * Intervals are grouped by `concept_id` and ordered by start time, so each
 * entry's positional index matches the start-sorted realization index used by
 * buildSpeakerForm / AnnotateView and handleDeleteInterval. Letters are assigned
 * by that same start rank (A = earliest). Each entry also carries the source
 * item (audition_prefix) and the IPA/ortho transcribed at that interval so the
 * UI can disambiguate recordings that legitimately collapse onto one canonical
 * concept_id (e.g. the same gloss elicited in two surveys).
 */
export function buildElicitationDetailsByConceptKey(
  record: AnnotationRecord | null | undefined,
): Record<string, ElicitationDetail[]> {
  const conceptIntervals = record?.tiers?.concept?.intervals ?? [];
  const ipaIntervals = record?.tiers?.ipa?.intervals ?? [];
  const orthoIntervals = record?.tiers?.ortho?.intervals ?? [];

  const byConcept = new Map<string, AnnotationInterval[]>();
  for (const interval of conceptIntervals) {
    const key = interval.concept_id == null ? '' : String(interval.concept_id).trim();
    if (!key) continue;
    const list = byConcept.get(key) ?? [];
    list.push(interval);
    byConcept.set(key, list);
  }

  const result: Record<string, ElicitationDetail[]> = {};
  for (const [key, list] of byConcept) {
    const sorted = [...list].sort((left, right) => (left.start - right.start) || (left.end - right.end));
    const labels = assignVariantLetters(sorted);
    result[key] = sorted.map((interval, index) => ({
      label: labels[index] ?? '',
      sourceItem: String(interval.audition_prefix ?? '').trim(),
      ipa: textOverlapping(ipaIntervals, interval),
      ortho: textOverlapping(orthoIntervals, interval),
    }));
  }
  return result;
}
