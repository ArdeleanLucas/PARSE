// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import {
  parseReferenceFormList,
  resolveReferenceFormLists,
  resolveFormSelection,
} from './referenceFormParsing';
import { parseReferenceFormList as parseReferenceFormListFromParseUI } from '../ParseUI';

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

  it('routes by ISO 15924 script hint when provided (Latn -> ipa slot)', () => {
    // A bare-string Latin form gets the IPA slot when the language is
    // declared Latn, regardless of what the Unicode classifier guesses.
    const entries = parseReferenceFormList(['maːʔ'], 'Latn');
    expect(entries[0].ipa).toBe('maːʔ');
    expect(entries[0].script).toBe('');
  });

  it('routes by ISO 15924 script hint (non-Latn -> script slot)', () => {
    // Even Latin-looking text routes to script when the language is
    // declared e.g. "Cyrl" -- the hint trumps the regex.
    const entries = parseReferenceFormList(['voda'], 'Cyrl');
    expect(entries[0].script).toBe('voda');
    expect(entries[0].ipa).toBe('');
  });

  it('explicit ipa/script field labels override the script hint', () => {
    // If a provider explicitly labels its fields, trust them. The hint
    // is a guide for *bare* strings, not a global override.
    const entries = parseReferenceFormList(
      [{ ipa: 'maːʔ', script: 'ماء' }],
      'Arab',
    );
    expect(entries[0].ipa).toBe('maːʔ');
    expect(entries[0].script).toBe('ماء');
  });

  it('falls back to Unicode regex when no hint is given (Cyrillic)', () => {
    // Cyrillic is in the expanded NON_LATIN_SCRIPT_RE safety net.
    const entries = parseReferenceFormList(['вода']);
    expect(entries[0].script).toBe('вода');
    expect(entries[0].ipa).toBe('');
  });

  it('falls back to Unicode regex when no hint is given (Bengali)', () => {
    const entries = parseReferenceFormList(['জল']);
    expect(entries[0].script).toBe('জল');
    expect(entries[0].ipa).toBe('');
  });

  it('falls back to Unicode regex when no hint is given (Ethiopic)', () => {
    const entries = parseReferenceFormList(['ውሃ']);
    expect(entries[0].script).toBe('ውሃ');
    expect(entries[0].ipa).toBe('');
  });

  it('does NOT classify Greek-block chars as script in the regex fallback (IPA overlap)', () => {
    // β (U+03B2) is both a Greek letter and a valid IPA letter. Without
    // a script hint, we keep it in the IPA slot to avoid breaking
    // phonetic strings like "βaba" that use IPA's beta.
    const entries = parseReferenceFormList(['βaba']);
    expect(entries[0].ipa).toBe('βaba');
    expect(entries[0].script).toBe('');
  });

  it('classifies Greek strings as script when the Grek hint is present', () => {
    // Greek-script languages (ell, grc) get correct routing via the
    // script-hint path even though the regex fallback can't tell.
    const entries = parseReferenceFormList(['νερό'], 'Grek');
    expect(entries[0].script).toBe('νερό');
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

  it('threads per-language script hints into the parser', () => {
    // tgk (Tajik) is Cyrillic in the modern script. Without a hint a
    // bare "вода" still lands in the script slot via the regex
    // fallback, but with the hint we get the deterministic path.
    const enrichments = {
      reference_forms: { water: { tgk: ['вода'] } },
    };
    const lists = resolveReferenceFormLists(enrichments, {}, concept, ['tgk'], { tgk: 'Cyrl' });
    expect(lists.tgk[0].script).toBe('вода');
    expect(lists.tgk[0].ipa).toBe('');
  });

  it('uses Latn hint to route bare Latin forms into the IPA slot', () => {
    // English (eng, Latn) bare-string form -- without any hint the
    // regex fallback already sends Latin to IPA, but the deterministic
    // hint makes the intent explicit and catches edge cases the regex
    // misses (mixed strings, etc.).
    const enrichments = {
      reference_forms: { water: { eng: ['waːtər'] } },
    };
    const lists = resolveReferenceFormLists(enrichments, {}, concept, ['eng'], { eng: 'Latn' });
    expect(lists.eng[0].ipa).toBe('waːtər');
    expect(lists.eng[0].script).toBe('');
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

describe('ParseUI compatibility re-export', () => {
  it('keeps parseReferenceFormList importable from ParseUI', () => {
    expect(parseReferenceFormListFromParseUI(['maːʔ'])).toEqual(parseReferenceFormList(['maːʔ']));
  });
});
