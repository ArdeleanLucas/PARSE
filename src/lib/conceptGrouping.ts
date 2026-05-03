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
  const match = conceptEn.match(/\s+([A-Z])\s*$/);
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

export function groupConceptEntries(
  rawConcepts: readonly ConceptEntry[],
  resolveTag: ResolveConceptTag,
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

  return grouped;
}
