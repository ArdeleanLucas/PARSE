import type { ConceptEntry } from '../api/types';
import type { Concept, ConceptVariant } from './speakerForm';
import type { ConceptTag } from './parseUIUtils';

type ResolveConceptTag = (conceptKeys: readonly string[]) => ConceptTag;
type ResolveVariantTag = (conceptKey: string) => ConceptTag;

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

function groupedConceptKey(
  sourceItem: string,
  sourceSurvey: string | undefined,
  sourceItemsWithMultipleGroupedBuckets: ReadonlySet<string>,
): string {
  if (!sourceItemsWithMultipleGroupedBuckets.has(sourceItem)) return sourceItem;
  const survey = normalizeSourceSurvey(sourceSurvey) ?? 'unspecified';
  return `source:${survey}:${sourceItem}`;
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

export function findConceptByUnderlyingKey(concepts: readonly Concept[], underlyingKey: string): Concept | undefined {
  return concepts.find((concept) => {
    if (concept.mergedKeys?.includes(underlyingKey)) return true;
    if (concept.variants?.some((variant) => variant.conceptKey === underlyingKey)) return true;
    return concept.key === underlyingKey;
  });
}

export function groupConceptEntries(
  rawConcepts: readonly ConceptEntry[],
  resolveTag: ResolveConceptTag,
  conceptMerges?: Record<string, readonly string[]>,
  resolveVariantTag?: ResolveVariantTag,
): Concept[] {
  const sourceBuckets = new Map<string, number[]>();
  const sourceBucketKeysByItem = new Map<string, Set<string>>();
  rawConcepts.forEach((entry, index) => {
    const sourceItem = normalizeSourceItem(entry.source_item);
    if (!sourceItem) return;
    const bucketKey = sourceBucketKey(sourceItem, entry.source_survey);
    const bucket = sourceBuckets.get(bucketKey) ?? [];
    bucket.push(index);
    sourceBuckets.set(bucketKey, bucket);
    const bucketKeys = sourceBucketKeysByItem.get(sourceItem) ?? new Set<string>();
    bucketKeys.add(bucketKey);
    sourceBucketKeysByItem.set(sourceItem, bucketKeys);
  });

  const sourceItemsWithMultipleGroupedBuckets = new Set<string>();
  for (const [sourceItem, bucketKeys] of sourceBucketKeysByItem.entries()) {
    const groupedBucketCount = Array.from(bucketKeys).filter((bucketKey) => (sourceBuckets.get(bucketKey)?.length ?? 0) >= 2).length;
    if (groupedBucketCount >= 2) sourceItemsWithMultipleGroupedBuckets.add(sourceItem);
  }

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
      key: groupedConceptKey(sourceItem, entry.source_survey, sourceItemsWithMultipleGroupedBuckets),
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
