import { describe, expect, it } from 'vitest';
import type { ConceptEntry } from '../api/types';
import { groupConceptEntries } from './conceptGrouping';

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
      id: 3,
      key: 'concept-c',
      name: 'sister of husband',
      sourceSurvey: 'KLQ',
    });
    expect(grouped[1].sourceItem).toBe('2.16');
    expect(grouped[1].variants).toBeUndefined();
    expect(grouped[2]).toMatchObject({ id: 4, key: 'concept-d', name: 'water' });
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
});
