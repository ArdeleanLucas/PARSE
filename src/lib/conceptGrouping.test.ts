import { describe, expect, it } from 'vitest';
import type { ConceptEntry } from '../api/types';
import { findConceptByUnderlyingKey, groupConceptEntries } from './conceptGrouping';

const untagged = () => 'untagged' as const;

describe('groupConceptEntries', () => {
  it('groups sibling concepts by source_item and derives the bare variant stem', () => {
    const entries: ConceptEntry[] = [
      { id: 'concept-a', label: 'brother of husband A', source_item: '2.15', source_survey: 'KLQ', custom_order: 10 },
      { id: 'concept-b', label: 'brother of husband B', source_item: '2.15', source_survey: 'KLQ', custom_order: 11 },
      { id: 'concept-c', label: 'sister of husband', source_item: '2.16', source_survey: 'KLQ', custom_order: 12 },
      { id: 'concept-d', label: 'water' },
    ];

    const grouped = groupConceptEntries(entries, untagged);

    expect(grouped).toHaveLength(3);
    expect(grouped[0]).toMatchObject({
      id: 1,
      key: '2.15',
      name: 'brother of husband',
      sourceItem: '2.15',
      sourceSurvey: 'KLQ',
      customOrder: 10,
    });
    expect(grouped[0].variants).toEqual([
      { conceptKey: 'concept-a', conceptEn: 'brother of husband A', variantLabel: 'A' },
      { conceptKey: 'concept-b', conceptEn: 'brother of husband B', variantLabel: 'B' },
    ]);
    expect(grouped[1]).toMatchObject({
      id: 2,
      key: 'concept-c',
      name: 'sister of husband',
      sourceSurvey: 'KLQ',
    });
    expect(grouped[1].sourceItem).toBe('2.16');
    expect(grouped[1].variants).toBeUndefined();
    expect(grouped[2]).toMatchObject({ id: 3, key: 'concept-d', name: 'water' });
  });

  it('groups non-adjacent source_item siblings while preserving the position of the first sibling', () => {
    const entries: ConceptEntry[] = [
      { id: 'a', label: 'brother of husband A', source_item: '2.15' },
      { id: 'c', label: 'sister-in-law', source_item: '2.16' },
      { id: 'b', label: 'brother of husband B', source_item: '2.15' },
    ];
    const grouped = groupConceptEntries(entries, untagged);
    expect(grouped).toHaveLength(2);
    expect(grouped[0].name).toBe('brother of husband');
    expect(grouped[0].variants).toHaveLength(2);
    expect(grouped[0].variants?.map(v => v.conceptKey)).toEqual(['a', 'b']);
    expect(grouped[1].key).toBe('c');
    expect(grouped[1].name).toBe('sister-in-law');
  });

  it('emits contiguous concept ids regardless of how many siblings are absorbed', () => {
    const entries: ConceptEntry[] = [
      { id: 'a', label: 'brother A', source_item: '2.15' },
      { id: 'b', label: 'brother B', source_item: '2.15' },
      { id: 'c', label: 'sister', source_item: '2.16' },
      { id: 'd', label: 'water' },
    ];
    const grouped = groupConceptEntries(entries, untagged);
    expect(grouped.map(g => g.id)).toEqual([1, 2, 3]);
  });

  it('uses sequential variant labels when concept_en has no trailing capital suffix', () => {
    const grouped = groupConceptEntries([
      { id: 'a', label: 'field gloss alpha', source_item: '9.1' },
      { id: 'b', label: 'field gloss beta', source_item: '9.1' },
      { id: 'c', label: 'field gloss gamma', source_item: '9.1' },
    ], untagged);

    expect(grouped).toHaveLength(1);
    expect(grouped[0].variants?.map((variant) => variant.variantLabel)).toEqual(['A', 'B', 'C']);
  });

  it('leaves missing, blank, and single-child source_item rows as singleton concepts', () => {
    const entries: ConceptEntry[] = [
      { id: 'a', label: 'blank source', source_item: '   ' },
      { id: 'b', label: 'missing source' },
      { id: 'c', label: 'only child', source_item: '3.1' },
    ];

    const grouped = groupConceptEntries(entries, untagged);

    expect(grouped).toHaveLength(3);
    expect(grouped.map((concept) => concept.key)).toEqual(['a', 'b', 'c']);
    expect(grouped.every((concept) => concept.variants === undefined)).toBe(true);
    expect(grouped[0].sourceItem).toBeUndefined();
    expect(grouped[1].sourceItem).toBeUndefined();
    expect(grouped[2].sourceItem).toBe('3.1');
  });

  it('applies explicit concept merges across singleton concepts and preserves contiguous ids', () => {
    const entries: ConceptEntry[] = [
      { id: '247', label: 'head (A)' },
      { id: '248', label: 'head (B)' },
      { id: '527', label: 'head' },
      { id: '600', label: 'water' },
    ];

    const grouped = groupConceptEntries(entries, untagged, { '527': ['247', '248'] });

    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({ id: 1, key: '527', name: 'head' });
    expect(grouped[0].mergedKeys).toEqual(['527', '247', '248']);
    expect(grouped[0].mergeAbsorbedNames).toEqual(['head (A)', 'head (B)']);
    expect(grouped.map((concept) => concept.id)).toEqual([1, 2]);
    expect(grouped.map((concept) => concept.key)).toEqual(['527', '600']);
  });

  it('merges a source-item grouped concept with a bare-stem singleton concept', () => {
    const entries: ConceptEntry[] = [
      { id: '247', label: 'head A', source_item: '2.47', source_survey: 'KLQ' },
      { id: '248', label: 'head B', source_item: '2.47', source_survey: 'KLQ' },
      { id: '527', label: 'head' },
    ];

    const grouped = groupConceptEntries(entries, untagged, { '2.47': ['527'] });

    expect(grouped).toHaveLength(1);
    expect(grouped[0].key).toBe('2.47');
    expect(grouped[0].mergedKeys).toEqual(['247', '248', '527']);
    expect(grouped[0].mergeAbsorbedNames).toEqual(['head']);
    expect(grouped[0].variants?.map((variant) => variant.conceptKey)).toEqual(['247', '248']);
  });

  it('silently skips stale absorbed concept keys while applying the rest of a merge', () => {
    const grouped = groupConceptEntries([
      { id: 'primary', label: 'head' },
      { id: 'absorbed', label: 'head (A)' },
      { id: 'water', label: 'water' },
    ], untagged, { primary: ['missing', 'absorbed'] });

    expect(grouped.map((concept) => concept.key)).toEqual(['primary', 'water']);
    expect(grouped[0].mergedKeys).toEqual(['primary', 'absorbed']);
    expect(grouped[0].mergeAbsorbedNames).toEqual(['head (A)']);
  });

  it('ignores empty merge override arrays', () => {
    const grouped = groupConceptEntries([
      { id: 'primary', label: 'head' },
      { id: 'absorbed', label: 'head (A)' },
    ], untagged, { primary: [] });

    expect(grouped).toHaveLength(2);
    expect(grouped[0].mergedKeys).toBeUndefined();
    expect(grouped.map((concept) => concept.key)).toEqual(['primary', 'absorbed']);
  });

});

describe('findConceptByUnderlyingKey', () => {
  it('returns the singleton concept when key matches concept.key', () => {
    const concepts = groupConceptEntries([
      { id: '527', label: 'head' },
      { id: '600', label: 'water' },
    ], untagged);

    expect(findConceptByUnderlyingKey(concepts, '600')?.name).toBe('water');
  });

  it('returns the source-item grouped concept when key matches any variant conceptKey', () => {
    const concepts = groupConceptEntries([
      { id: '247', label: 'head A', source_item: '2.47', source_survey: 'KLQ' },
      { id: '248', label: 'head B', source_item: '2.47', source_survey: 'KLQ' },
      { id: '600', label: 'water' },
    ], untagged);

    expect(findConceptByUnderlyingKey(concepts, '248')?.key).toBe('2.47');
  });

  it('returns the merged primary when key matches any mergedKey', () => {
    const concepts = groupConceptEntries([
      { id: '247', label: 'head (A)' },
      { id: '248', label: 'head (B)' },
      { id: '527', label: 'head' },
    ], untagged, { '527': ['247', '248'] });

    expect(findConceptByUnderlyingKey(concepts, '248')?.key).toBe('527');
  });

  it('returns undefined when key matches nothing', () => {
    const concepts = groupConceptEntries([
      { id: '527', label: 'head' },
    ], untagged);

    expect(findConceptByUnderlyingKey(concepts, 'missing')).toBeUndefined();
  });
});
