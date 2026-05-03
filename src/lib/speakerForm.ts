import type { AnnotationInterval, AnnotationRecord } from '../api/types';
import { isRecord, overlaps, pickOrthoIntervalForConcept } from './parseUIUtils';
import type { ConceptTag } from './parseUIUtils';

export interface ConceptVariant {
  conceptKey: string;
  conceptEn: string;
  variantLabel: string;
}

export interface Concept {
  id: number;
  key: string;
  name: string;
  tag: ConceptTag;
  sourceItem?: string;
  sourceSurvey?: string;
  customOrder?: number;
  variants?: ConceptVariant[];
}

export interface Realization {
  ipa: string;
  ortho: string;
  startSec: number | null;
  endSec: number | null;
}

export interface SpeakerForm {
  speaker: string;
  ipa: string;
  ortho: string;
  utterances: number;
  variantCount: number;
  similarityByLang: Record<string, number | null>;
  cognate: string;
  flagged: boolean;
  startSec: number | null;
  endSec: number | null;
  realizations: Realization[];
  selectedIdx: number;
  realizationsSource: 'source-item' | 'auto-detect' | 'single';
}

function emptyRealization(): Realization {
  return { ipa: '', ortho: '', startSec: null, endSec: null };
}

function realizationFromIpaInterval(record: AnnotationRecord | null | undefined, ipaInterval: AnnotationInterval): Realization {
  return {
    ipa: ipaInterval.text ?? '',
    ortho: record ? pickOrthoIntervalForConcept(record, ipaInterval)?.text ?? '' : '',
    startSec: typeof ipaInterval.start === 'number' ? ipaInterval.start : null,
    endSec: typeof ipaInterval.end === 'number' ? ipaInterval.end : null,
  };
}

function intervalDuration(interval: AnnotationInterval): number {
  if (typeof interval.start !== 'number' || typeof interval.end !== 'number') return 0;
  return Math.max(0, interval.end - interval.start);
}

function pickLongestInterval(intervals: readonly AnnotationInterval[]): AnnotationInterval | null {
  let best: AnnotationInterval | null = null;
  let bestDuration = -1;
  for (const interval of intervals) {
    const duration = intervalDuration(interval);
    if (duration > bestDuration) {
      best = interval;
      bestDuration = duration;
    }
  }
  return best;
}

function conceptIntervalsForKey(record: AnnotationRecord | null | undefined, conceptKey: string): AnnotationInterval[] {
  return (record?.tiers.concept?.intervals ?? []).filter((interval) => String(interval.concept_id ?? '') === conceptKey);
}

function conceptIntervalMatchesSpeakerFormConcept(concept: Concept, interval: AnnotationInterval): boolean {
  const intervalConceptId = String(interval.concept_id ?? '');
  if (concept.variants?.length) {
    return concept.variants.some((variant) => variant.conceptKey === intervalConceptId);
  }
  return concept.key === intervalConceptId;
}

function ipaIntervalsForConceptIntervals(record: AnnotationRecord | null | undefined, conceptIntervals: readonly AnnotationInterval[]): AnnotationInterval[] {
  const ipaIntervals = record?.tiers.ipa?.intervals ?? [];
  return ipaIntervals.filter((ipaInterval) => conceptIntervals.some((conceptInterval) => overlaps(ipaInterval, conceptInterval)));
}

function buildSingleRealizationForVariant(
  record: AnnotationRecord | null | undefined,
  conceptKey: string,
): Realization {
  const variantConceptIntervals = conceptIntervalsForKey(record, conceptKey);
  const variantIpaIntervals = ipaIntervalsForConceptIntervals(record, variantConceptIntervals);
  const longest = pickLongestInterval(variantIpaIntervals);
  return longest ? realizationFromIpaInterval(record, longest) : emptyRealization();
}

function readCanonicalOverride(
  canonicalOverrides: Record<string, unknown> | null,
  overrideKey: string,
  speaker: string,
  realizationCount: number,
): number {
  if (realizationCount <= 0) return 0;
  const conceptCanonical = canonicalOverrides && isRecord(canonicalOverrides[overrideKey])
    ? canonicalOverrides[overrideKey] as Record<string, unknown>
    : null;
  const rawIdx = conceptCanonical?.[speaker];
  const requestedIdx = typeof rawIdx === 'number' && Number.isInteger(rawIdx) && rawIdx >= 0 ? rawIdx : 0;
  return Math.min(requestedIdx, realizationCount - 1);
}

function readAutoDetectDismissed(
  overrides: Record<string, unknown> | null,
  conceptKey: string,
  speaker: string,
): boolean {
  const dismissedRoot = overrides && isRecord(overrides.auto_detect_dismissed)
    ? overrides.auto_detect_dismissed as Record<string, unknown>
    : null;
  const conceptDismissed = dismissedRoot && isRecord(dismissedRoot[conceptKey])
    ? dismissedRoot[conceptKey] as Record<string, unknown>
    : null;
  return conceptDismissed?.[speaker] === true;
}

export function buildSpeakerForm(
  record: AnnotationRecord | null | undefined,
  concept: Concept,
  speaker: string,
  enrichments: Record<string, unknown>,
  flagged: boolean,
  primaryContactCodes: readonly string[],
): SpeakerForm {
  const conceptIntervals = (record?.tiers.concept?.intervals ?? []).filter((interval) => conceptIntervalMatchesSpeakerFormConcept(concept, interval));
  const matchingIpaIntervals = ipaIntervalsForConceptIntervals(record, conceptIntervals);
  const utterances = matchingIpaIntervals.length;

  const similarityRoot = isRecord(enrichments.similarity) ? enrichments.similarity : null;
  const conceptSimilarity = similarityRoot && isRecord(similarityRoot[concept.key]) ? similarityRoot[concept.key] as Record<string, unknown> : null;
  const speakerSimilarity = conceptSimilarity && isRecord(conceptSimilarity[speaker]) ? conceptSimilarity[speaker] as Record<string, unknown> : null;
  // The backend's compute_similarity_scores writes
  //   similarity[concept][speaker][lang] = { score: number|null,
  //                                          has_reference_data: bool }
  // An earlier revision treated this inner object as if it were a bare
  // number (and read "tr" for Persian), which made every column silently
  // resolve to 0 regardless of compute state. Reading .score from the
  // object -- and using the CLEF-config code "fa" for Persian, not "tr"
  // -- is what actually surfaces the computed distances in the UI.
  // Returns null (not 0) when the score is missing so the UI can render
  // "—" and distinguish "not yet computed" from "computed zero".
  const rawSim = (code: string): number | null => {
    const cell = speakerSimilarity?.[code];
    if (!isRecord(cell)) return null;
    const score = (cell as Record<string, unknown>).score;
    return typeof score === 'number' ? score : null;
  };
  const similarityByLang: Record<string, number | null> = {};
  for (const code of primaryContactCodes) {
    similarityByLang[code] = rawSim(code);
  }

  const overrides = isRecord(enrichments.manual_overrides) ? enrichments.manual_overrides as Record<string, unknown> : null;
  const overrideSets = overrides && isRecord(overrides.cognate_sets) ? overrides.cognate_sets as Record<string, unknown> : null;
  const autoSets = isRecord(enrichments.cognate_sets) ? enrichments.cognate_sets as Record<string, unknown> : null;
  // Manual overrides win over auto-computed cognate sets.
  const conceptCognates = (overrideSets && isRecord(overrideSets[concept.key]) ? overrideSets[concept.key] : null)
    ?? (autoSets && isRecord(autoSets[concept.key]) ? autoSets[concept.key] : null);
  let cognate: SpeakerForm['cognate'] = '—';
  if (conceptCognates && isRecord(conceptCognates)) {
    // Accept any single-letter group A–Z; first match wins.
    for (const [group, members] of Object.entries(conceptCognates)) {
      if (Array.isArray(members) && members.includes(speaker) && /^[A-Z]$/.test(group)) {
        cognate = group;
        break;
      }
    }
  }

  // Per-speaker flag: overrides.speaker_flags[conceptKey][speaker] = true.
  const flagsBlock = overrides && isRecord(overrides.speaker_flags) ? overrides.speaker_flags as Record<string, unknown> : null;
  const conceptFlags = flagsBlock && isRecord(flagsBlock[concept.key]) ? flagsBlock[concept.key] as Record<string, unknown> : null;
  const speakerFlagged = !!(conceptFlags && conceptFlags[speaker]);

  const primaryConceptInterval = conceptIntervals[0] ?? null;
  // Prefer word-level ortho_words over the coarse ortho tier — see the
  // rationale on pickOrthoIntervalForConcept above.
  const orthoText = record && primaryConceptInterval
    ? pickOrthoIntervalForConcept(record, primaryConceptInterval)?.text ?? ''
    : '';

  const canonicalOverrides = overrides && isRecord(overrides.canonical_realizations)
    ? overrides.canonical_realizations as Record<string, unknown>
    : null;

  if (concept.sourceItem && concept.variants && concept.variants.length >= 2) {
    const realizations = concept.variants.map((variant) => buildSingleRealizationForVariant(record, variant.conceptKey));
    const selectedIdx = readCanonicalOverride(canonicalOverrides, concept.sourceItem, speaker, realizations.length);
    const canonical = realizations[selectedIdx];
    return {
      speaker,
      ipa: canonical?.ipa ?? '',
      ortho: canonical?.ortho ?? orthoText,
      utterances,
      variantCount: realizations.length,
      similarityByLang,
      cognate,
      flagged: speakerFlagged || flagged,
      startSec: canonical?.startSec ?? null,
      endSec: canonical?.endSec ?? null,
      realizations,
      selectedIdx,
      realizationsSource: 'source-item',
    };
  }

  // pickOrthoIntervalForConcept is strict to the passed interval, so each realization only shows IPA-aligned ortho.
  let realizations: Realization[] = matchingIpaIntervals.map((ipaInterval) => realizationFromIpaInterval(record, ipaInterval));
  let realizationsSource: SpeakerForm['realizationsSource'] = realizations.length > 1 ? 'auto-detect' : 'single';
  let selectedIdx = readCanonicalOverride(canonicalOverrides, concept.key, speaker, realizations.length);

  if (realizations.length > 1 && readAutoDetectDismissed(overrides, concept.key, speaker)) {
    const longest = pickLongestInterval(matchingIpaIntervals);
    realizations = longest ? [realizationFromIpaInterval(record, longest)] : [];
    realizationsSource = 'single';
    selectedIdx = 0;
  }

  const canonical = realizations[selectedIdx];
  const variantCount = realizations.length;

  return {
    speaker,
    ipa: canonical?.ipa ?? '',
    ortho: canonical?.ortho ?? orthoText,
    utterances,
    variantCount,
    similarityByLang,
    cognate,
    flagged: speakerFlagged || flagged,
    startSec: canonical?.startSec ?? null,
    endSec: canonical?.endSec ?? null,
    realizations,
    selectedIdx,
    realizationsSource,
  };
}
