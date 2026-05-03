import type { ConceptEntry } from '../api/types';
import type { Concept, ConceptVariant } from './speakerForm';
import type { ConceptTag } from './parseUIUtils';

type ResolveConceptTag = (conceptKeys: readonly string[]) => ConceptTag;

function normalizeSourceItem(sourceItem: string | undefined): string | null {
  const trimmed = sourceItem?.trim() ?? '';
  return trimmed.length > 0 ? trimmed : null;
}

function fallbackVariantLabel(index: number): string {
  const code = 'A'.charCodeAt(0) + index;
  return code <= 'Z'.charCodeAt(0) ? String.fromCharCode(code) : String(index + 1);
}

function variantLabelFor(conceptEn: string, index: number): string {
  const match = conceptEn.match(/(?:\s+|\s*\()([A-Z])\)?\s*$/);
  return match?.[1] ?? fallbackVariantLabel(index);
}

function stripTrailingVariantSuffix(label: string): string {
  return label.replace(/\s+[A-Z]\s*$/, '').trimEnd();
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
  const prefixStem = stripTrailingVariantSuffix(longestCommonPrefix(labels));
  if (prefixStem.length > 0) return prefixStem;
  return stripTrailingVariantSuffix(labels[0] ?? '');
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
): Concept[] {
  const sourceBuckets = new Map<string, number[]>();
  rawConcepts.forEach((entry, index) => {
    const sourceItem = normalizeSourceItem(entry.source_item);
    if (!sourceItem) return;
    const bucket = sourceBuckets.get(sourceItem) ?? [];
    bucket.push(index);
    sourceBuckets.set(sourceItem, bucket);
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

    const siblings = sourceBuckets.get(sourceItem) ?? [];
    if (siblings.length < 2) {
      emittedId += 1;
      grouped.push(singletonConcept(entry, emittedId, resolveTag));
      return;
    }
    if (emittedSourceItems.has(sourceItem)) return;
    emittedSourceItems.add(sourceItem);
    emittedId += 1;

    const siblingEntries = siblings.map((siblingIndex) => rawConcepts[siblingIndex]);
    const variants: ConceptVariant[] = siblingEntries.map((sibling, siblingIndex) => ({
      conceptKey: sibling.id,
      conceptEn: sibling.label,
      variantLabel: variantLabelFor(sibling.label, siblingIndex),
    }));
    const conceptKeys = siblingEntries.map((sibling) => sibling.id);

    grouped.push({
      id: emittedId,
      key: sourceItem,
      name: variantStemFor(siblingEntries.map((sibling) => sibling.label)),
      tag: resolveTag(conceptKeys),
      sourceItem,
      sourceSurvey: entry.source_survey,
      customOrder: entry.custom_order,
      variants,
    });
  });


  const activeMerges = Object.entries(conceptMerges ?? {}).filter(([, absorbed]) => absorbed.length > 0);
  if (activeMerges.length === 0) return grouped;

  const underlyingKeys = (concept: Concept): string[] => concept.variants?.map((variant) => variant.conceptKey) ?? [concept.key];
  const underlyingVariants = (concept: Concept, startIndex: number): ConceptVariant[] => {
    if (concept.variants?.length) return concept.variants;
    return [{ conceptKey: concept.key, conceptEn: concept.name, variantLabel: variantLabelFor(concept.name, startIndex) }];
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
