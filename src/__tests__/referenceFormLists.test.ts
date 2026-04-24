// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import {
  parseReferenceFormList,
  resolveReferenceFormLists,
  resolveFormSelection,
} from '../ParseUI';

// The single-form helpers in ParseUI power the Reference Forms panel's
// multi-form display + selection UI. These tests lock in the
// no-transliteration contract (Unicode-block classification only) and
// the round-trip through provenance / legacy shapes.

describe('parseReferenceFormList', () => {
  it('routes bare Arabic-script strings to the script slot', () => {
    const entries = parseReferenceFormList(['ماء']);
    expect(entries).toHaveLength(1);
    expect(entries[0]).toEqual({
      raw: 'ماء',
      script: 'ماء',
      ipa: '',
      audioUrl: null,
      sources: [],
    });
  });

  it('routes bare Latin/IPA strings to the ipa slot without touching the text', () => {
    const entries = parseReferenceFormList(['maːʔ']);
    expect(entries).toHaveLength(1);
    expect(entries[0].raw).toBe('maːʔ');
    expect(entries[0].ipa).toBe('maːʔ');
    expect(entries[0].script).toBe('');
  });

  it('handles the provenance {form, sources} shape verbatim', () => {
    const entries = parseReferenceFormList([
      { form: 'maːʔ', sources: ['wikidata', 'asjp'] },
    ]);
    expect(entries).toHaveLength(1);
    expect(entries[0].raw).toBe('maːʔ');
    expect(entries[0].ipa).toBe('maːʔ');
    expect(entries[0].sources).toEqual(['wikidata', 'asjp']);
  });

  it('classifies the provenance form by Unicode block too (no auto-conversion)', () => {
    // A provider writing script text into the "form" field shouldn't
    // silently get promoted to IPA just because the shape is new.
    const entries = parseReferenceFormList([
      { form: 'ماء', sources: ['wiktionary'] },
    ]);
    expect(entries[0].script).toBe('ماء');
    expect(entries[0].ipa).toBe('');
  });

  it('dedupes by raw text across multiple items', () => {
    const entries = parseReferenceFormList([
      { form: 'maːʔ', sources: ['asjp'] },
      'maːʔ',   // duplicate of the same string
      'muya',
    ]);
    expect(entries.map((e) => e.raw)).toEqual(['maːʔ', 'muya']);
  });

  it('trusts explicit field labels even when they contain script chars', () => {
    // If a provider labels a field "ipa", we display it as IPA even
    // when the string contains script-range chars -- that is the
    // provider's claim and overrides the Unicode classifier.
    const entries = parseReferenceFormList([{ ipa: 'māʔ', script: 'ماء' }]);
    expect(entries[0].ipa).toBe('māʔ');
    expect(entries[0].script).toBe('ماء');
  });

  it('returns an empty list for null/undefined/empty inputs', () => {
    expect(parseReferenceFormList(null)).toEqual([]);
    expect(parseReferenceFormList(undefined)).toEqual([]);
    expect(parseReferenceFormList([])).toEqual([]);
    expect(parseReferenceFormList([''])).toEqual([]);
  });
});

describe('resolveReferenceFormLists', () => {
  const concept = { id: 1, key: '1', name: 'water', tag: 'untagged' as const };

  it('prefers enrichments.reference_forms over the SIL fallback', () => {
    const enrichments = {
      reference_forms: {
        water: {
          ar: [{ form: 'maːʔ', sources: ['wikidata'] }, { form: 'ماء', sources: ['wiktionary'] }],
        },
      },
    };
    const silConcepts = {
      ar: { water: ['stale'] },
    };
    const lists = resolveReferenceFormLists(enrichments, silConcepts, concept, ['ar']);
    expect(lists.ar.map((e) => e.raw)).toEqual(['maːʔ', 'ماء']);
  });

  it('falls back to the SIL contact-language config when enrichments are empty', () => {
    const enrichments = {};
    const silConcepts = {
      ar: { water: [{ form: 'maːʔ', sources: ['asjp'] }] },
    };
    const lists = resolveReferenceFormLists(enrichments, silConcepts, concept, ['ar']);
    expect(lists.ar).toHaveLength(1);
    expect(lists.ar[0].sources).toEqual(['asjp']);
  });

  it('omits languages with no populated forms at all', () => {
    const lists = resolveReferenceFormLists({}, {}, concept, ['ar', 'fa']);
    expect(lists).toEqual({});
  });
});

describe('resolveFormSelection', () => {
  it('returns null when no selection is set (default = all selected)', () => {
    expect(resolveFormSelection({}, 'water', 'ar')).toBeNull();
    expect(resolveFormSelection({ form_selections: {} }, 'water', 'ar')).toBeNull();
    expect(resolveFormSelection({ form_selections: { fire: {} } }, 'water', 'ar')).toBeNull();
  });

  it('returns an empty array for explicit opt-out', () => {
    const meta = { form_selections: { water: { ar: [] } } };
    expect(resolveFormSelection(meta, 'water', 'ar')).toEqual([]);
  });

  it('returns the allow-list for explicit subset selections', () => {
    const meta = { form_selections: { water: { ar: ['ماء'] } } };
    expect(resolveFormSelection(meta, 'water', 'ar')).toEqual(['ماء']);
  });

  it('filters out non-string entries defensively', () => {
    const meta = { form_selections: { water: { ar: ['ماء', 42, null] } } };
    expect(resolveFormSelection(meta, 'water', 'ar')).toEqual(['ماء']);
  });
});
