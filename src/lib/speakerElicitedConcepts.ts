import type { AnnotationRecord } from '../api/types';

interface ConceptKeyCarrier {
  key?: string | null;
  mergedKeys?: readonly (string | null | undefined)[] | null;
  variants?: readonly { conceptKey?: string | null }[] | null;
  mergedVariants?: readonly { conceptKey?: string | null }[] | null;
}

export function speakerElicitedConceptKeys(
  record: AnnotationRecord | null | undefined,
): Set<string> {
  const keys = new Set<string>();
  for (const interval of record?.tiers?.concept?.intervals ?? []) {
    const key = interval.concept_id == null ? '' : String(interval.concept_id).trim();
    if (key) keys.add(key);
  }
  return keys;
}

export function conceptUnderlyingKeys(concept: ConceptKeyCarrier): string[] {
  const keys = new Set<string>();
  const add = (value: string | null | undefined) => {
    const key = value == null ? '' : String(value).trim();
    if (key) keys.add(key);
  };
  const hasVariants =
    (concept.variants?.length ?? 0) > 0 ||
    (concept.mergedVariants?.length ?? 0) > 0;
  // concept.key for grouped rows is the source_item string identifier, not a real
  // concept_id; including it in concept_id-keyed lookups (e.g. speakerSortKeys)
  // produces collisions when a source_item happens to equal another concept's
  // concept_id (e.g. "this JBIL 298" colliding with "dog (A)" concept_id 298).
  // Only include concept.key for singleton rows where it IS the concept_id.
  if (!hasVariants) add(concept.key);
  for (const key of concept.mergedKeys ?? []) add(key);
  for (const variant of concept.variants ?? []) add(variant.conceptKey);
  for (const variant of concept.mergedVariants ?? []) add(variant.conceptKey);
  return Array.from(keys);
}

export function conceptMatchesElicitedKeys(
  concept: ConceptKeyCarrier,
  elicitedConceptKeys: ReadonlySet<string>,
): boolean {
  if (elicitedConceptKeys.size === 0) return false;
  return conceptUnderlyingKeys(concept).some((key) => elicitedConceptKeys.has(key));
}
