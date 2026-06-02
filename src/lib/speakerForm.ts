import type { AnnotationInterval, AnnotationRecord, ConceptSurveyLinks } from '../api/types';
import { isRecord, overlaps, pickOrthoIntervalForConcept } from './parseUIUtils';
import type { ConceptTag } from './parseUIUtils';

export interface ConceptVariant {
  conceptKey: string;
  conceptEn: string;
  variantLabel: string;
  surveys?: ConceptSurveyLinks;
  /** Per-variant status used by the concept sidebar when grouped siblings diverge. */
  tag?: ConceptTag;
}

export interface Concept {
  id: number;
  key: string;
  name: string;
  tag: ConceptTag;
  sourceItem?: string;
  sourceSurvey?: string;
  customOrder?: number;
  surveys?: ConceptSurveyLinks;
  variants?: ConceptVariant[];
  mergedKeys?: string[];
  mergedVariants?: ConceptVariant[];
  mergeAbsorbedNames?: string[];
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
  /** Raw concept id used for cognate and similarity reads. */
  cognateKey?: string;
  /** UID key used for per-speaker flag round-trip; v1 is concept+speaker and can later add a stable realization qualifier. */
  flagKey?: string;
  flagged: boolean;
  startSec: number | null;
  endSec: number | null;
  realizations: Realization[];
  selectedIdx: number;
  realizationsSource: 'source-item' | 'auto-detect' | 'merged' | 'single';
  /**
   * True when the canonical realization's start (or end) sits past
   * `record.source_audio_duration_sec`. Surfaced so the UI can grey the row
   * and disable playback when the working WAV doesn't yet cover the
   * timestamp (e.g. Khan01 manifest-derived intervals beyond the WAV's
   * 8590s end before the multi-WAV concat lands).
   */
  pastEndOfAudio: boolean;
}

function computePastEndOfAudio(
  record: AnnotationRecord | null | undefined,
  startSec: number | null,
  endSec: number | null,
): boolean {
  const dur = record?.source_audio_duration_sec;
  if (typeof dur !== 'number' || !Number.isFinite(dur) || dur <= 0) return false;
  if (typeof startSec === 'number' && startSec >= dur) return true;
  if (typeof endSec === 'number' && endSec > dur) return true;
  return false;
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

function sortIntervalsByStart(intervals: readonly AnnotationInterval[]): AnnotationInterval[] {
  return [...intervals].sort((left, right) => (left.start - right.start) || (left.end - right.end));
}

function conceptIntervalsForKey(record: AnnotationRecord | null | undefined, conceptKey: string): AnnotationInterval[] {
  return sortIntervalsByStart((record?.tiers?.concept?.intervals ?? []).filter((interval) => String(interval.concept_id ?? '') === conceptKey));
}

function conceptIntervalMatchesSpeakerFormConcept(concept: Concept, interval: AnnotationInterval): boolean {
  const intervalConceptId = String(interval.concept_id ?? '');
  if (concept.mergedKeys?.length) {
    return concept.mergedKeys.includes(intervalConceptId);
  }
  if (concept.variants?.length) {
    return concept.variants.some((variant) => variant.conceptKey === intervalConceptId);
  }
  return concept.key === intervalConceptId;
}

function ipaIntervalsForConceptIntervals(record: AnnotationRecord | null | undefined, conceptIntervals: readonly AnnotationInterval[]): AnnotationInterval[] {
  const ipaIntervals = record?.tiers?.ipa?.intervals ?? [];
  return sortIntervalsByStart(ipaIntervals.filter((ipaInterval) => conceptIntervals.some((conceptInterval) => overlaps(ipaInterval, conceptInterval))));
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

function readFocusedIntervalIndex(
  focusedIntervalIndex: number | undefined,
  realizationCount: number,
): number | null {
  if (realizationCount <= 0) return null;
  if (typeof focusedIntervalIndex !== 'number' || !Number.isInteger(focusedIntervalIndex) || focusedIntervalIndex < 0) return null;
  return focusedIntervalIndex < realizationCount ? focusedIntervalIndex : 0;
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

function readCompareDecisionFields(
  enrichments: Record<string, unknown>,
  cognateKey: string,
  speaker: string,
  primaryContactCodes: readonly string[],
): Pick<SpeakerForm, 'similarityByLang' | 'cognate'> {
  const similarityRoot = isRecord(enrichments.similarity) ? enrichments.similarity : null;
  const conceptSimilarity = similarityRoot && isRecord(similarityRoot[cognateKey]) ? similarityRoot[cognateKey] as Record<string, unknown> : null;
  const speakerSimilarity = conceptSimilarity && isRecord(conceptSimilarity[speaker]) ? conceptSimilarity[speaker] as Record<string, unknown> : null;
  // The backend's compute_similarity_scores writes
  //   similarity[concept][speaker][lang] = { score: number|null,
  //                                          has_reference_data: bool }
  // keyed by raw numeric concept_id. Grouped concepts expose that selected
  // numeric id as cognateKey; their display key may be only a source_item.
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
  const conceptCognates = (overrideSets && isRecord(overrideSets[cognateKey]) ? overrideSets[cognateKey] : null)
    ?? (autoSets && isRecord(autoSets[cognateKey]) ? autoSets[cognateKey] : null);
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

  return { similarityByLang, cognate };
}

function readSpeakerFlag(
  enrichments: Record<string, unknown>,
  flagKey: string,
  speaker: string,
): boolean {
  const overrides = isRecord(enrichments.manual_overrides) ? enrichments.manual_overrides as Record<string, unknown> : null;
  // Per-speaker flag v1: overrides.speaker_flags[conceptUid][speaker] = true.
  // Keep this concept+speaker key centralized so a future stable realization
  // qualifier can be added without changing component call sites.
  const flagsBlock = overrides && isRecord(overrides.speaker_flags) ? overrides.speaker_flags as Record<string, unknown> : null;
  const conceptFlags = flagsBlock && isRecord(flagsBlock[flagKey]) ? flagsBlock[flagKey] as Record<string, unknown> : null;
  return !!(conceptFlags && conceptFlags[speaker]);
}

export function buildSpeakerForm(
  record: AnnotationRecord | null | undefined,
  concept: Concept,
  speaker: string,
  enrichments: Record<string, unknown>,
  primaryContactCodes: readonly string[],
  focusedConceptId?: string | null,
  focusedIntervalIndex?: number,
): SpeakerForm {
  const conceptIntervals = sortIntervalsByStart((record?.tiers?.concept?.intervals ?? []).filter((interval) => conceptIntervalMatchesSpeakerFormConcept(concept, interval)));
  const matchingIpaIntervals = ipaIntervalsForConceptIntervals(record, conceptIntervals);
  const utterances = matchingIpaIntervals.length;

  const overrides = isRecord(enrichments.manual_overrides) ? enrichments.manual_overrides as Record<string, unknown> : null;

  const primaryConceptInterval = conceptIntervals[0] ?? null;
  // Prefer word-level ortho_words over the coarse ortho tier — see the
  // rationale on pickOrthoIntervalForConcept above.
  const orthoText = record && primaryConceptInterval
    ? pickOrthoIntervalForConcept(record, primaryConceptInterval)?.text ?? ''
    : '';

  /** @deprecated scheduled for removal once decision files predating 2026-05 stop appearing. */
  const canonicalOverrides = overrides && isRecord(overrides.canonical_realizations)
    // Legacy canonical_realizations read path: scheduled for removal once decision files predating 2026-05 stop appearing.
    ? overrides.canonical_realizations as Record<string, unknown>
    : null;

  if (concept.mergedKeys && concept.mergedKeys.length > 1) {
    const realizations = concept.mergedKeys.map((key) => buildSingleRealizationForVariant(record, key));
    const focusedIdx = focusedConceptId ? concept.mergedKeys.indexOf(focusedConceptId) : -1;
    const selectedIdx = focusedIdx >= 0
      ? focusedIdx
      : readCanonicalOverride(canonicalOverrides, concept.key, speaker, realizations.length);
    const canonical = realizations[selectedIdx];
    const cognateKey = concept.mergedKeys[selectedIdx] ?? concept.key;
    const flagKey = concept.key;
    const decision = readCompareDecisionFields(enrichments, cognateKey, speaker, primaryContactCodes);
    return {
      speaker,
      ipa: canonical?.ipa ?? '',
      ortho: canonical?.ortho ?? orthoText,
      utterances,
      variantCount: realizations.length,
      similarityByLang: decision.similarityByLang,
      cognateKey,
      flagKey,
      cognate: decision.cognate,
      flagged: readSpeakerFlag(enrichments, flagKey, speaker),
      startSec: canonical?.startSec ?? null,
      endSec: canonical?.endSec ?? null,
      realizations,
      selectedIdx,
      realizationsSource: 'merged',
      pastEndOfAudio: computePastEndOfAudio(record, canonical?.startSec ?? null, canonical?.endSec ?? null),
    };
  }

  if (concept.sourceItem && concept.variants && concept.variants.length >= 2) {
    const realizations = concept.variants.map((variant) => buildSingleRealizationForVariant(record, variant.conceptKey));
    const focusedIdx = focusedConceptId ? concept.variants.findIndex((variant) => variant.conceptKey === focusedConceptId) : -1;
    const selectedIdx = focusedIdx >= 0
      ? focusedIdx
      : readCanonicalOverride(canonicalOverrides, concept.key, speaker, realizations.length);
    const canonical = realizations[selectedIdx];
    const cognateKey = concept.variants[selectedIdx]?.conceptKey ?? concept.key;
    const flagKey = concept.key;
    const decision = readCompareDecisionFields(enrichments, cognateKey, speaker, primaryContactCodes);
    return {
      speaker,
      ipa: canonical?.ipa ?? '',
      ortho: canonical?.ortho ?? orthoText,
      utterances,
      variantCount: realizations.length,
      similarityByLang: decision.similarityByLang,
      cognateKey,
      flagKey,
      cognate: decision.cognate,
      flagged: readSpeakerFlag(enrichments, flagKey, speaker),
      startSec: canonical?.startSec ?? null,
      endSec: canonical?.endSec ?? null,
      realizations,
      selectedIdx,
      realizationsSource: 'source-item',
      pastEndOfAudio: computePastEndOfAudio(record, canonical?.startSec ?? null, canonical?.endSec ?? null),
    };
  }

  // pickOrthoIntervalForConcept is strict to the passed interval, so each realization only shows IPA-aligned ortho.
  let realizations: Realization[] = matchingIpaIntervals.map((ipaInterval) => realizationFromIpaInterval(record, ipaInterval));
  let realizationsSource: SpeakerForm['realizationsSource'] = realizations.length > 1 ? 'auto-detect' : 'single';
  let selectedIdx = focusedConceptId === concept.key
    ? readFocusedIntervalIndex(focusedIntervalIndex, realizations.length) ?? readCanonicalOverride(canonicalOverrides, concept.key, speaker, realizations.length)
    : readCanonicalOverride(canonicalOverrides, concept.key, speaker, realizations.length);

  if (realizations.length > 1 && readAutoDetectDismissed(overrides, concept.key, speaker)) {
    const longest = pickLongestInterval(matchingIpaIntervals);
    realizations = longest ? [realizationFromIpaInterval(record, longest)] : [];
    realizationsSource = 'single';
    selectedIdx = 0;
  }

  const canonical = realizations[selectedIdx];
  const variantCount = realizations.length;
  const cognateKey = concept.key;
  const flagKey = concept.key;
  const decision = readCompareDecisionFields(enrichments, cognateKey, speaker, primaryContactCodes);

  return {
    speaker,
    ipa: canonical?.ipa ?? '',
    ortho: canonical?.ortho ?? orthoText,
    utterances,
    variantCount,
    similarityByLang: decision.similarityByLang,
    cognateKey,
    flagKey,
    cognate: decision.cognate,
    flagged: readSpeakerFlag(enrichments, flagKey, speaker),
    startSec: canonical?.startSec ?? null,
    endSec: canonical?.endSec ?? null,
    realizations,
    selectedIdx,
    realizationsSource,
    pastEndOfAudio: computePastEndOfAudio(record, canonical?.startSec ?? null, canonical?.endSec ?? null),
  };
}
