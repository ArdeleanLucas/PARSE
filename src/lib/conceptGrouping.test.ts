import { describe, expect, it } from 'vitest';
import type { ConceptEntry, ConceptIdentityResponse } from '../api/types';
import { buildRealizationKey, classifyConceptIdentity, findConceptByUnderlyingKey, groupConceptEntries, parseRealizationKey, resolveModeSwitchSelection } from './conceptGrouping';

const untagged = () => 'untagged' as const;


describe('realization keys', () => {
  it('formats and parses per-realization keys', () => {
    const key = buildRealizationKey('247', 1);

    expect(key).toBe('247:1');
    expect(parseRealizationKey(key)).toEqual({ conceptId: '247', intervalIndex: 1 });
  });

  it('parses concept ids that contain colons by splitting at the final colon', () => {
    expect(parseRealizationKey('source:JBIL:79:0')).toEqual({ conceptId: 'source:JBIL:79', intervalIndex: 0 });
  });

  it('returns null for empty or malformed keys', () => {
    expect(parseRealizationKey(null)).toBeNull();
    expect(parseRealizationKey('')).toBeNull();
    expect(parseRealizationKey('247:not-a-number')).toBeNull();
  });
});

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
      // Key is the canonical member id (first in declaration order for
      // non-numeric ids), never the survey-local source_item "2.15".
      key: 'concept-a',
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

  it('stamps per-variant tags from each underlying concept key while preserving the parent rollup', () => {
    const grouped = groupConceptEntries([
      { id: 'hair-a', label: 'hair (A)', source_item: '1.1' },
      { id: 'hair-c', label: 'hair (C)', source_item: '1.1' },
    ], () => 'problematic' as const, undefined, (conceptKey) => conceptKey === 'hair-a' ? 'untagged' as const : 'problematic' as const);

    expect(grouped).toHaveLength(1);
    expect(grouped[0].tag).toBe('problematic');
    expect(grouped[0].variants?.map((variant) => [variant.conceptKey, variant.tag])).toEqual([
      ['hair-a', 'untagged'],
      ['hair-c', 'problematic'],
    ]);
  });

  it('stamps per-variant tags on compare mergedVariants for singleton merges', () => {
    const grouped = groupConceptEntries([
      { id: 'primary', label: 'hair' },
      { id: 'absorbed', label: 'hair (A)' },
    ], () => 'confirmed' as const, { primary: ['absorbed'] }, (conceptKey) => conceptKey === 'absorbed' ? 'review' as const : 'confirmed' as const);

    expect(grouped[0].tag).toBe('confirmed');
    expect(grouped[0].mergedVariants?.map((variant) => [variant.conceptKey, variant.tag])).toEqual([
      ['primary', 'confirmed'],
      ['absorbed', 'review'],
    ]);
  });
  it('threads plural survey links through grouped and singleton concepts', () => {
    const entries: ConceptEntry[] = [
      { id: 'concept-a', label: 'rain A', source_item: 'KLQ_1.10', source_survey: 'KLQ', surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' } },
      { id: 'concept-b', label: 'rain B', source_item: 'KLQ_1.10', source_survey: 'KLQ', surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' } },
      { id: 'concept-c', label: 'fire', source_item: 'KLQ_2.1', source_survey: 'KLQ', surveys: { klq: 'KLQ_2.1' } },
    ];

    const grouped = groupConceptEntries(entries, untagged);

    expect(grouped[0]).toMatchObject({ key: 'concept-a', surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' } });
    expect(grouped[1]).toMatchObject({ key: 'concept-c', surveys: { klq: 'KLQ_2.1' } });
  });

  it('does not group equal source item numbers from different surveys', () => {
    const entries: ConceptEntry[] = [
      { id: '88', label: 'white', source_item: '5.1', source_survey: 'KLQ' },
      { id: '563', label: 'The boy cut the rope with a knife !', source_item: '5.1', source_survey: 'EXT' },
      { id: '596', label: 'The boy cut the rope with a knife', source_item: '5.1', source_survey: 'EXT' },
    ];

    const grouped = groupConceptEntries(entries, untagged);

    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({ key: '88', name: 'white', sourceSurvey: 'KLQ', sourceItem: '5.1' });
    expect(grouped[0].variants).toBeUndefined();
    expect(grouped[1]).toMatchObject({ key: '563', sourceSurvey: 'EXT', sourceItem: '5.1' });
    expect(grouped[1].variants?.map((variant) => variant.conceptKey)).toEqual(['563', '596']);
  });

  it('keeps grouped concept keys unique when multiple surveys share an item number', () => {
    const entries: ConceptEntry[] = [
      { id: '88a', label: 'white A', source_item: '5.1', source_survey: 'KLQ' },
      { id: '88b', label: 'white B', source_item: '5.1', source_survey: 'KLQ' },
      { id: '563', label: 'The boy cut the rope with a knife !', source_item: '5.1', source_survey: 'EXT' },
      { id: '596', label: 'The boy cut the rope with a knife', source_item: '5.1', source_survey: 'EXT' },
    ];

    const grouped = groupConceptEntries(entries, untagged);

    expect(grouped).toHaveLength(2);
    // Distinct canonical member ids disambiguate the two same-item buckets
    // naturally — no synthetic `source:` prefix needed, and never the shared
    // source_item "5.1".
    expect(grouped.map((concept) => concept.key)).toEqual(['88a', '563']);
    expect(grouped.map((concept) => concept.sourceItem)).toEqual(['5.1', '5.1']);
    expect(grouped.map((concept) => concept.sourceSurvey)).toEqual(['KLQ', 'EXT']);
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

  it('groups three explicit variants into one n-ary source-item concept', () => {
    const grouped = groupConceptEntries([
      { id: '365', label: 'new (A)', source_item: '154', source_survey: 'JBIL' },
      { id: '618', label: 'new (B)', source_item: '154', source_survey: 'JBIL' },
      { id: '619', label: 'new (C)', source_item: '154', source_survey: 'JBIL' },
    ], untagged);

    expect(grouped).toHaveLength(1);
    expect(grouped[0].name).toBe('new');
    expect(grouped[0].variants).toEqual([
      { conceptKey: '365', conceptEn: 'new (A)', variantLabel: 'A' },
      { conceptKey: '618', conceptEn: 'new (B)', variantLabel: 'B' },
      { conceptKey: '619', conceptEn: 'new (C)', variantLabel: 'C' },
    ]);
  });

  it('keeps numeric fallback suffix variants with their numeric labels', () => {
    const grouped = groupConceptEntries([
      { id: '900', label: 'shape (26)', source_item: '8.8' },
      { id: '901', label: 'shape (27)', source_item: '8.8' },
    ], untagged);

    expect(grouped).toHaveLength(1);
    expect(grouped[0].name).toBe('shape');
    expect(grouped[0].variants?.map((variant) => variant.variantLabel)).toEqual(['26', '27']);
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

    // The merge is keyed by the group's canonical key ('247'), as the UI now
    // emits it — not the legacy source_item key '2.47'.
    const grouped = groupConceptEntries(entries, untagged, { '247': ['527'] });

    expect(grouped).toHaveLength(1);
    expect(grouped[0].key).toBe('247');
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


  it('uses backend concept identity uids as displayed concept keys and keeps row ids as variants', () => {
    const grouped = groupConceptEntries([
      { id: '92', label: 'yellow', source_item: '5.5', source_survey: 'KLQ' },
      { id: '167', label: 'yellow (A)', source_item: '178', source_survey: 'JBIL' },
      { id: '311', label: 'bird (A)', source_item: '92', source_survey: 'JBIL' },
      { id: '651', label: 'bird (B)', source_item: '92', source_survey: 'JBIL' },
    ], untagged, undefined, undefined, {
      version: 1,
      concepts: [
        { uid: 'c-bird', label: 'bird', members: ['311', '651'], origin: 'auto' },
        { uid: 'c-yellow', label: 'yellow', members: ['92', '167'], origin: 'auto' },
      ],
      uid_by_row: { '311': 'c-bird', '651': 'c-bird', '92': 'c-yellow', '167': 'c-yellow' },
      warnings: [],
    });

    expect(grouped).toHaveLength(2);
    expect(grouped.map((concept) => concept.key)).toEqual(['c-bird', 'c-yellow']);
    expect(grouped[0]).toMatchObject({ id: 1, key: 'c-bird', name: 'bird', sourceItem: '92', sourceSurvey: 'JBIL' });
    expect(grouped[0].variants?.map((variant) => [variant.conceptKey, variant.conceptEn, variant.variantLabel])).toEqual([
      ['311', 'bird (A)', 'A'],
      ['651', 'bird (B)', 'B'],
    ]);
  });

  it('uses identity membership rather than frontend source-item buckets', () => {
    const grouped = groupConceptEntries([
      { id: '45', label: 'ice', source_item: '123', source_survey: 'JBIL' },
      { id: '144', label: 'snow', source_item: '123', source_survey: 'JBIL' },
      { id: '123', label: 'to jump', source_item: '6.7', source_survey: 'KLQ' },
    ], untagged, undefined, undefined, {
      version: 1,
      concepts: [
        { uid: 'c-45', label: 'ice', members: ['45'], origin: 'manual:split' },
        { uid: 'c-144', label: 'snow', members: ['144'], origin: 'manual:split' },
        { uid: 'c-123', label: 'to jump', members: ['123'], origin: 'auto' },
      ],
      uid_by_row: { '45': 'c-45', '144': 'c-144', '123': 'c-123' },
      warnings: [],
    });

    expect(grouped.map((concept) => concept.key)).toEqual(['c-45', 'c-144', 'c-123']);
    expect(grouped.map((concept) => concept.variants?.map((variant) => variant.conceptKey))).toEqual([['45'], ['144'], ['123']]);
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

    expect(findConceptByUnderlyingKey(concepts, '248')?.key).toBe('247');
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

describe('resolveModeSwitchSelection (open-in-annotate / mode-switch reconcile)', () => {
  // "big" is a grouped concept: variants A (concept-a) and B (concept-b) share
  // one source_item; "water" is a separate singleton concept.
  const concepts = groupConceptEntries(
    [
      { id: 'concept-a', label: 'big A', source_item: '4.1', source_survey: 'KLQ', custom_order: 1 },
      { id: 'concept-b', label: 'big B', source_item: '4.1', source_survey: 'KLQ', custom_order: 2 },
      { id: 'concept-d', label: 'water' },
    ],
    untagged,
  );
  const big = concepts[0]; // id 1, key '4.1', variants concept-a / concept-b
  const water = concepts[1]; // singleton

  it('preserves the realization when the resolver is seeded with the clicked variant (the fix)', () => {
    // Seeded: rawKeyToResolve === selectedConceptKey === the clicked variant B.
    const res = resolveModeSwitchSelection(concepts, 'concept-b', big.id, 'concept-b');
    expect(res.realizationKey).toBeUndefined(); // no reset → chosen index kept
    expect(res.conceptId).toBeUndefined(); // already on the owning concept
  });

  it('clobbers a non-primary selection back to A when NOT seeded (documents the bug)', () => {
    // Unseeded: resolver runs with the prior/primary key while the user picked B.
    const res = resolveModeSwitchSelection(concepts, 'concept-a', big.id, 'concept-b');
    expect(res.realizationKey).toBe(buildRealizationKey('concept-a', 0));
  });

  it('navigates conceptId to the concept that owns the seeded key', () => {
    const res = resolveModeSwitchSelection(concepts, 'concept-d', big.id, 'concept-d');
    expect(res.conceptId).toBe(water.id);
    expect(res.realizationKey).toBeUndefined();
  });

  it('returns no-op for a null or unknown key', () => {
    expect(resolveModeSwitchSelection(concepts, null, big.id, null)).toEqual({});
    expect(resolveModeSwitchSelection(concepts, 'nope', big.id, 'nope')).toEqual({});
  });
});

describe('classifyConceptIdentity', () => {
  const usable: ConceptIdentityResponse = {
    version: 1,
    concepts: [{ uid: 'c-1', label: 'one', members: ['1'], origin: 'auto' }],
    uid_by_row: { '1': 'c-1' },
    warnings: [],
  };
  const emptyIdentity: ConceptIdentityResponse = { version: 1, concepts: [], uid_by_row: {}, warnings: [] };

  it("is 'loaded' when identity carries concepts (even alongside a stale error)", () => {
    expect(classifyConceptIdentity(usable, null)).toBe('loaded');
    expect(classifyConceptIdentity(usable, 'boom')).toBe('loaded');
  });

  it("is 'unavailable' when identity failed to load (null payload + error)", () => {
    expect(classifyConceptIdentity(null, 'network down')).toBe('unavailable');
  });

  it("is 'empty' for a legitimately-empty identity or the pre-load transient", () => {
    // Loaded-but-empty (mocks / older backends) and the not-yet-loaded state are
    // both safe to treat as empty; only a load error is 'unavailable'.
    expect(classifyConceptIdentity(emptyIdentity, null)).toBe('empty');
    expect(classifyConceptIdentity(null, null)).toBe('empty');
  });
});
