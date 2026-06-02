import type { ConceptEntry, ConceptIdentityResponse } from '../api/types';
import type { Concept, ConceptVariant } from './speakerForm';
import type { ConceptTag } from './parseUIUtils';

type ResolveConceptTag = (conceptKeys: readonly string[]) => ConceptTag;
type ResolveVariantTag = (conceptKey: string) => ConceptTag;

/**
 * Format a per-realization selection key. A realization is one annotation
 * interval on one (speaker, concept_id) pair. The interval_index is the
 * position in the speaker's intervals on that concept_id sorted by start
 * (matches assignVariantLetters input ordering, so chip letter A maps to
 * interval_index 0).
 */
export function buildRealizationKey(conceptId: string, intervalIndex: number): string {
  return `${conceptId}:${intervalIndex}`;
}

export function parseRealizationKey(key: string | null): { conceptId: string; intervalIndex: number } | null {
  if (!key) return null;
  const separatorIndex = key.lastIndexOf(':');
  if (separatorIndex <= 0 || separatorIndex === key.length - 1) return null;
  const conceptId = key.slice(0, separatorIndex);
  const intervalIndex = Number(key.slice(separatorIndex + 1));
  if (!conceptId || !Number.isFinite(intervalIndex)) return null;
  return { conceptId, intervalIndex };
}

function withVariantTag(
  variant: Omit<ConceptVariant, 'tag'>,
  resolveVariantTag: ResolveVariantTag | undefined,
): ConceptVariant {
  return resolveVariantTag ? { ...variant, tag: resolveVariantTag(variant.conceptKey) } : variant;
}

function normalizeSourceItem(sourceItem: string | undefined): string | null {
  const trimmed = sourceItem?.trim() ?? '';
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeSourceSurvey(sourceSurvey: string | undefined): string | null {
  const trimmed = sourceSurvey?.trim() ?? '';
  return trimmed.length > 0 ? trimmed : null;
}

function sourceBucketKey(sourceItem: string, sourceSurvey: string | undefined): string {
  const survey = normalizeSourceSurvey(sourceSurvey) ?? '';
  return `${survey}\u0000${sourceItem}`;
}

/**
 * A grouped concept's storage key is the canonical csv id of its members — the
 * minimum numeric id, mirroring the backend #529 identity migration
 * (`canonical_id = min(ids)`).
 *
 * This is load-bearing: a concept's `key` is the persistence key for every
 * per-concept decision (speaker_flags, cognate_sets, concept tags,
 * borrowing_flags, canonical selections). It MUST live in a single,
 * collision-free namespace. csv `id`s are unique by construction (the concepts
 * table primary key); `source_item` is a survey-local coordinate that shares a
 * string namespace with csv ids and silently collides — e.g. JBIL
 * `source_item "123"` equals csv id `123` ("to jump"), so keying the
 * `ice`+`snow` group on "123" made it share a flag slot with "to jump". Keying
 * on a member id can never collide with another concept: the member rows belong
 * to this group and to no other concept.
 */
function canonicalConceptKey(memberIds: readonly string[]): string {
  let best: string | null = null;
  let bestNum = Number.POSITIVE_INFINITY;
  for (const id of memberIds) {
    const n = Number(id);
    if (Number.isFinite(n)) {
      if (n < bestNum) {
        bestNum = n;
        best = id;
      }
    } else if (best === null) {
      // Non-numeric ids are not expected in the live corpus; fall back to the
      // first member in declaration order so the key is still deterministic.
      best = id;
    }
  }
  return best ?? memberIds[0] ?? '';
}

function fallbackVariantLabel(index: number): string {
  const code = 'A'.charCodeAt(0) + index;
  return code <= 'Z'.charCodeAt(0) ? String.fromCharCode(code) : String(index + 1);
}

function variantLabelFor(conceptEn: string, index: number): string {
  const match = conceptEn.match(/(?:\s*\(([A-Z]|\d+)\)|\s+([A-Z]|\d+))\s*$/);
  return match?.[1] ?? match?.[2] ?? fallbackVariantLabel(index);
}

function letterForVariantRank(rank: number): string {
  let n = rank;
  let label = '';
  do {
    label = String.fromCharCode('A'.charCodeAt(0) + (n % 26)) + label;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return label;
}

/**
 * Assign per-speaker variant letters to intervals for the same concept_id.
 * Variant letters are computed from start-time rank and returned in input order.
 */
export function assignVariantLetters(intervals: ReadonlyArray<{ start: number }>): string[] {
  if (intervals.length === 0) return [];
  if (intervals.length === 1) return [''];

  const indexed = intervals.map((interval, index) => ({ start: interval.start, index }));
  // Break start-time ties by original index so assignment is stable across runtimes.
  indexed.sort((a, b) => (a.start - b.start) || (a.index - b.index));

  const letters = new Array<string>(intervals.length);
  indexed.forEach(({ index }, rank) => {
    letters[index] = letterForVariantRank(rank);
  });
  return letters;
}

function stripTrailingVariantSuffix(label: string): string {
  return label
    .replace(/\s*\(([A-Z]|\d+)\)\s*$/, '')
    .replace(/\s+([A-Z]|\d+)\s*$/, '')
    .trimEnd();
}

function stripDanglingVariantPunctuation(label: string): string {
  return label.replace(/[\s(]+$/, '').trimEnd();
}

function longestCommonPrefix(values: readonly string[]): string {
  if (values.length === 0) return '';
  let prefix = values[0] ?? '';
  for (const value of values.slice(1)) {
    let end = 0;
    const max = Math.min(prefix.length, value.length);
    while (end < max && prefix[end] === value[end]) end += 1;
    prefix = prefix.slice(0, end);
    if (prefix.length === 0) break;
  }
  return prefix;
}

function variantStemFor(labels: readonly string[]): string {
  const strippedLabels = labels.map((label) => stripTrailingVariantSuffix(label));
  const commonStem = stripDanglingVariantPunctuation(longestCommonPrefix(strippedLabels));
  if (commonStem.length > 0) return commonStem;
  return stripDanglingVariantPunctuation(strippedLabels[0] ?? '');
}

function singletonConcept(entry: ConceptEntry, emittedId: number, resolveTag: ResolveConceptTag): Concept {
  const sourceItem = normalizeSourceItem(entry.source_item) ?? undefined;
  return {
    id: emittedId,
    key: entry.id,
    name: entry.label,
    tag: resolveTag([entry.id]),
    sourceItem,
    sourceSurvey: sourceItem ? entry.source_survey : undefined,
    customOrder: entry.custom_order,
    surveys: entry.surveys,
  };
}

function cleanIdentityString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function isUsableConceptIdentity(identity: ConceptIdentityResponse | null | undefined): identity is ConceptIdentityResponse {
  return !!identity && Array.isArray(identity.concepts) && identity.concepts.length > 0;
}

/**
 * How concept identity resolved for the current view:
 *  - `loaded`      — identity is present with at least one concept; group and
 *                    route by stable `uid`.
 *  - `empty`       — identity loaded successfully but carries no concepts
 *                    (mocks / older backends that don't serve identity yet).
 *                    The legacy `(survey, source_item)` grouping and the
 *                    `row_ids.includes` bundle fallback are valid here.
 *  - `unavailable` — identity FAILED to load (network/server error). This is
 *                    NOT interchangeable with `empty`: the legacy grouping may
 *                    still be shown for display, but the collision-prone
 *                    `row_ids.includes` bundle routing MUST NOT be used, because
 *                    it can silently attach a concept to the wrong bundle.
 */
export type ConceptIdentityAvailability = 'loaded' | 'empty' | 'unavailable';

/**
 * Classify the concept-identity load outcome so consumers can tell a
 * legitimately-empty identity apart from one that failed to load. Identity
 * presence wins: a usable payload is always `loaded` regardless of any stale
 * error. A load error with no usable payload is `unavailable`; everything else
 * (including the pre-load transient) is `empty`.
 */
export function classifyConceptIdentity(
  identity: ConceptIdentityResponse | null | undefined,
  loadError: string | null | undefined,
): ConceptIdentityAvailability {
  if (isUsableConceptIdentity(identity)) return 'loaded';
  if (loadError) return 'unavailable';
  return 'empty';
}

function groupConceptEntriesFromIdentity(
  rawConcepts: readonly ConceptEntry[],
  resolveTag: ResolveConceptTag,
  resolveVariantTag: ResolveVariantTag | undefined,
  identity: ConceptIdentityResponse,
): Concept[] {
  const entriesByRowId = new Map(rawConcepts.map((entry) => [String(entry.id), entry]));
  const grouped: Concept[] = [];
  let emittedId = 0;

  for (const identityConcept of identity.concepts) {
    const uid = cleanIdentityString(identityConcept.uid);
    if (!uid) continue;
    const memberIds = identityConcept.members.map(cleanIdentityString).filter(Boolean);
    const memberEntries = memberIds
      .map((rowId) => entriesByRowId.get(rowId))
      .filter((entry): entry is ConceptEntry => !!entry);
    if (memberEntries.length === 0) continue;

    emittedId += 1;
    const firstEntry = memberEntries[0];
    const sourceItem = normalizeSourceItem(firstEntry.source_item) ?? undefined;
    const variants: ConceptVariant[] = memberEntries.map((entry, index) => withVariantTag({
      conceptKey: entry.id,
      conceptEn: entry.label,
      variantLabel: variantLabelFor(entry.label, index),
      surveys: entry.surveys,
    }, resolveVariantTag));

    grouped.push({
      id: emittedId,
      key: uid,
      name: cleanIdentityString(identityConcept.label) || variantStemFor(memberEntries.map((entry) => entry.label)),
      tag: resolveTag([uid, ...memberIds]),
      sourceItem,
      sourceSurvey: sourceItem ? firstEntry.source_survey : undefined,
      customOrder: firstEntry.custom_order,
      surveys: firstEntry.surveys,
      variants,
    });
  }

  return grouped;
}

export function findConceptByUnderlyingKey(concepts: readonly Concept[], underlyingKey: string): Concept | undefined {
  return concepts.find((concept) => {
    if (concept.mergedKeys?.includes(underlyingKey)) return true;
    if (concept.variants?.some((variant) => variant.conceptKey === underlyingKey)) return true;
    return concept.key === underlyingKey;
  });
}

/** Outcome of reconciling the active concept/realization across a mode switch. */
export interface ModeSwitchSelection {
  /** Navigate to this concept id (absent = leave conceptId unchanged). */
  conceptId?: number;
  /** Reset the selected realization to this key (absent = leave it intact). */
  realizationKey?: string;
}

/**
 * On a mode switch the concept rows collapse/expand, so the previously-active
 * underlying key (`rawKeyToResolve`) is reconciled back to whichever concept now
 * owns it. Behaviour:
 *  - navigate `conceptId` to the owning concept when it differs;
 *  - reset the realization to that concept's first interval ONLY when the
 *    current selection (`selectedConceptKey`) points somewhere else.
 *
 * The reset condition is what makes "Open in annotate" work for grouped
 * concepts: seed `rawKeyToResolve` with the clicked row's key so it equals
 * `selectedConceptKey`, and the realization index is left intact (no reset to 0)
 * while still navigating to the right concept. Without seeding, the resolver
 * runs with the prior concept's key and clobbers a non-primary selection back to
 * variant/realization A.
 */
export function resolveModeSwitchSelection(
  concepts: readonly Concept[],
  rawKeyToResolve: string | null,
  currentConceptId: number,
  selectedConceptKey: string | null,
): ModeSwitchSelection {
  if (!rawKeyToResolve) return {};
  const next = findConceptByUnderlyingKey(concepts, rawKeyToResolve);
  if (!next) return {};
  const out: ModeSwitchSelection = {};
  if (next.id !== currentConceptId) out.conceptId = next.id;
  if (selectedConceptKey !== rawKeyToResolve) out.realizationKey = buildRealizationKey(rawKeyToResolve, 0);
  return out;
}

export function groupConceptEntries(
  rawConcepts: readonly ConceptEntry[],
  resolveTag: ResolveConceptTag,
  conceptMerges?: Record<string, readonly string[]>,
  resolveVariantTag?: ResolveVariantTag,
  conceptIdentity?: ConceptIdentityResponse | null,
  options?: { identityUnavailable?: boolean },
): Concept[] {
  if (isUsableConceptIdentity(conceptIdentity)) {
    return groupConceptEntriesFromIdentity(rawConcepts, resolveTag, resolveVariantTag, conceptIdentity);
  }

  if (options?.identityUnavailable) {
    return rawConcepts.map((entry, index) => singletonConcept(entry, index + 1, resolveTag));
  }

  const sourceBuckets = new Map<string, number[]>();
  rawConcepts.forEach((entry, index) => {
    const sourceItem = normalizeSourceItem(entry.source_item);
    if (!sourceItem) return;
    const bucketKey = sourceBucketKey(sourceItem, entry.source_survey);
    const bucket = sourceBuckets.get(bucketKey) ?? [];
    bucket.push(index);
    sourceBuckets.set(bucketKey, bucket);
  });

  const grouped: Concept[] = [];
  const emittedSourceItems = new Set<string>();
  let emittedId = 0;
  rawConcepts.forEach((entry) => {
    const sourceItem = normalizeSourceItem(entry.source_item);
    if (!sourceItem) {
      emittedId += 1;
      grouped.push(singletonConcept(entry, emittedId, resolveTag));
      return;
    }

    const bucketKey = sourceBucketKey(sourceItem, entry.source_survey);
    const siblings = sourceBuckets.get(bucketKey) ?? [];
    if (siblings.length < 2) {
      emittedId += 1;
      grouped.push(singletonConcept(entry, emittedId, resolveTag));
      return;
    }
    if (emittedSourceItems.has(bucketKey)) return;
    emittedSourceItems.add(bucketKey);
    emittedId += 1;

    const siblingEntries = siblings.map((siblingIndex) => rawConcepts[siblingIndex]);
    const variants: ConceptVariant[] = siblingEntries.map((sibling, siblingIndex) => withVariantTag({
      conceptKey: sibling.id,
      conceptEn: sibling.label,
      variantLabel: variantLabelFor(sibling.label, siblingIndex),
    }, resolveVariantTag));
    const conceptKeys = siblingEntries.map((sibling) => sibling.id);

    grouped.push({
      id: emittedId,
      key: canonicalConceptKey(conceptKeys),
      name: variantStemFor(siblingEntries.map((sibling) => sibling.label)),
      tag: resolveTag(conceptKeys),
      sourceItem,
      sourceSurvey: entry.source_survey,
      customOrder: entry.custom_order,
      surveys: entry.surveys,
      variants,
    });
  });


  const activeMerges = Object.entries(conceptMerges ?? {}).filter(([, absorbed]) => absorbed.length > 0);
  if (activeMerges.length === 0) return grouped;

  const underlyingKeys = (concept: Concept): string[] => concept.variants?.map((variant) => variant.conceptKey) ?? [concept.key];
  const underlyingVariants = (concept: Concept, startIndex: number): ConceptVariant[] => {
    if (concept.variants?.length) return concept.variants;
    return [withVariantTag({ conceptKey: concept.key, conceptEn: concept.name, variantLabel: variantLabelFor(concept.name, startIndex) }, resolveVariantTag)];
  };

  const absorbedConcepts = new Set<Concept>();
  for (const [primaryKey, absorbedKeys] of activeMerges) {
    const primary = findConceptByUnderlyingKey(grouped, primaryKey);
    if (!primary) continue;
    const absorbed = absorbedKeys
      .map((key) => findConceptByUnderlyingKey(grouped, key))
      .filter((concept): concept is Concept => !!concept && concept !== primary);
    if (absorbed.length === 0) continue;

    const mergedKeys = [...underlyingKeys(primary)];
    const mergedVariants = [...underlyingVariants(primary, 0)];
    const mergeAbsorbedNames: string[] = [];
    for (const concept of absorbed) {
      const startIndex = mergedKeys.length;
      mergedKeys.push(...underlyingKeys(concept));
      mergedVariants.push(...underlyingVariants(concept, startIndex));
      mergeAbsorbedNames.push(concept.name);
      absorbedConcepts.add(concept);
    }
    primary.mergedKeys = mergedKeys;
    primary.mergedVariants = mergedVariants;
    primary.mergeAbsorbedNames = mergeAbsorbedNames;
  }

  let nextId = 0;
  return grouped
    .filter((concept) => !absorbedConcepts.has(concept))
    .map((concept) => ({ ...concept, id: ++nextId }));
}
