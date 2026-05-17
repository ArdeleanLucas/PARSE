import { describe, expect, it } from 'vitest';
import type { ConceptEntry, Tag as StoreTag } from '../api/types';
import { groupConceptEntries } from './conceptGrouping';
import { getConceptStatus } from './parseUIUtils';

const STORE_TAGS: StoreTag[] = [
  { id: 'problematic', label: 'Problematic', color: '#ef4444' },
  { id: 'confirmed', label: 'Confirmed', color: '#10b981' },
];

function getTagsForSpeaker(conceptTagsForSpeaker: Record<string, string[]>, conceptKey: string): StoreTag[] {
  const applied = new Set(conceptTagsForSpeaker[conceptKey] ?? []);
  return STORE_TAGS.filter((tag) => applied.has(tag.id));
}

function groupWithVisibleParentTags(
  entries: ConceptEntry[],
  conceptTagsForSpeaker: Record<string, string[]>,
  visibleKeys: ReadonlySet<string>,
  freshKeys: ReadonlySet<string> = new Set(),
  scopedToSpeaker = true,
) {
  const resolveParentTag = (keys: readonly string[]) => {
    const parentKeys = scopedToSpeaker && visibleKeys.size > 0
      ? keys.filter((key) => visibleKeys.has(key) || freshKeys.has(key))
      : keys;
    return getConceptStatus(parentKeys.flatMap((key) => getTagsForSpeaker(conceptTagsForSpeaker, key)));
  };
  const resolveVariantTag = (key: string) => getConceptStatus(getTagsForSpeaker(conceptTagsForSpeaker, key));
  return groupConceptEntries(entries, resolveParentTag, undefined, resolveVariantTag);
}

describe('parent concept tag aggregation', () => {
  it('filters hidden Saha01 white variant tags out of the scoped parent dot', () => {
    const entries: ConceptEntry[] = [
      { id: 'white-a', label: 'white (A)', source_item: '181', source_survey: 'JBIL' },
      { id: 'white-b', label: 'white (B)', source_item: '181', source_survey: 'JBIL' },
    ];
    const grouped = groupWithVisibleParentTags(
      entries,
      { 'white-a': [], 'white-b': ['problematic'] },
      new Set(['white-a']),
    );

    expect(grouped[0].tag).toBe('untagged');
    expect(grouped[0].variants?.find((variant) => variant.conceptKey === 'white-b')?.tag).toBe('problematic');
  });

  it('filters hidden Qasr01 dog variant tags out of the scoped parent dot', () => {
    const entries: ConceptEntry[] = [
      { id: 'dog-a', label: 'dog (A)', source_item: '79', source_survey: 'JBIL' },
      { id: 'dog-b', label: 'dog (B)', source_item: '79', source_survey: 'JBIL' },
    ];
    const grouped = groupWithVisibleParentTags(
      entries,
      { 'dog-a': [], 'dog-b': ['problematic'] },
      new Set(['dog-a']),
    );

    expect(grouped[0].tag).toBe('untagged');
  });

  it('keeps visible problematic variants contributing to the scoped parent dot', () => {
    const entries: ConceptEntry[] = [
      { id: 'white-a', label: 'white (A)', source_item: '181', source_survey: 'JBIL' },
      { id: 'white-b', label: 'white (B)', source_item: '181', source_survey: 'JBIL' },
    ];
    const grouped = groupWithVisibleParentTags(
      entries,
      { 'white-a': ['problematic'], 'white-b': [] },
      new Set(['white-a']),
    );

    expect(grouped[0].tag).toBe('problematic');
  });

  it('leaves compare-mode aggregation unchanged when speaker scoping is off', () => {
    const entries: ConceptEntry[] = [
      { id: 'white-a', label: 'white (A)', source_item: '181', source_survey: 'JBIL' },
      { id: 'white-b', label: 'white (B)', source_item: '181', source_survey: 'JBIL' },
    ];
    const grouped = groupWithVisibleParentTags(
      entries,
      { 'white-a': [], 'white-b': ['problematic'] },
      new Set(['white-a']),
      new Set(),
      false,
    );

    expect(grouped[0].tag).toBe('problematic');
  });

  it('falls back to all variants when there is no elicitation data', () => {
    const entries: ConceptEntry[] = [
      { id: 'white-a', label: 'white (A)', source_item: '181', source_survey: 'JBIL' },
      { id: 'white-b', label: 'white (B)', source_item: '181', source_survey: 'JBIL' },
    ];
    const grouped = groupWithVisibleParentTags(
      entries,
      { 'white-a': [], 'white-b': ['problematic'] },
      new Set(),
    );

    expect(grouped[0].tag).toBe('problematic');
  });

  it('keeps fresh duplicate variants contributing to the scoped parent dot', () => {
    const entries: ConceptEntry[] = [
      { id: 'white-a', label: 'white (A)', source_item: '181', source_survey: 'JBIL' },
      { id: 'white-b', label: 'white (B)', source_item: '181', source_survey: 'JBIL' },
    ];
    const grouped = groupWithVisibleParentTags(
      entries,
      { 'white-a': [], 'white-b': ['problematic'] },
      new Set(['white-a']),
      new Set(['white-b']),
    );

    expect(grouped[0].tag).toBe('problematic');
  });
});
