import { describe, expect, it } from 'vitest';
import type { AnnotationInterval, AnnotationRecord } from '../api/types';
import { buildSpeakerForm } from './speakerForm';
import type { Concept } from './speakerForm';

function makeRecord(partial: {
  concept?: AnnotationInterval[];
  ipa?: AnnotationInterval[];
  ortho?: AnnotationInterval[];
  ortho_words?: AnnotationInterval[];
}): AnnotationRecord {
  return {
    speaker: 'Fail02',
    tiers: {
      ipa_phone: { name: 'ipa_phone', display_order: 1, intervals: [] },
      ipa: { name: 'ipa', display_order: 2, intervals: partial.ipa ?? [] },
      ortho: { name: 'ortho', display_order: 3, intervals: partial.ortho ?? [] },
      ortho_words: { name: 'ortho_words', display_order: 4, intervals: partial.ortho_words ?? [] },
      stt: { name: 'stt', display_order: 5, intervals: [] },
      concept: { name: 'concept', display_order: 6, intervals: partial.concept ?? [] },
      sentence: { name: 'sentence', display_order: 7, intervals: [] },
      speaker: { name: 'speaker', display_order: 8, intervals: [] },
    },
    source_wav: '',
  };
}

describe('buildSpeakerForm', () => {
  const concept = { id: 1, key: 'hair', name: 'Hair', tag: 'untagged' as const };

  it('builds a speaker row from matching concept/ipa intervals and language-specific similarity scores', () => {
    const record = makeRecord({
      concept: [{ start: 10, end: 10.5, text: 'hair', concept_id: 'hair' }],
      ipa: [{ start: 10.1, end: 10.4, text: 'muwi' }],
      ortho_words: [{ start: 10.15, end: 10.35, text: 'مووی' }],
      ortho: [{ start: 0, end: 100, text: 'coarse paragraph' }],
    });

    const enrichments = {
      similarity: {
        hair: {
          Fail02: {
            ar: { score: 0.9, has_reference_data: true },
            fa: { score: null, has_reference_data: false },
          },
        },
      },
    };

    expect(buildSpeakerForm(record, concept, 'Fail02', enrichments, false, ['ar', 'fa'])).toEqual({
      speaker: 'Fail02',
      ipa: 'muwi',
      ortho: 'مووی',
      utterances: 1,
      variantCount: 1,
      similarityByLang: { ar: 0.9, fa: null },
      cognate: '—',
      flagged: false,
      startSec: 10.1,
      endSec: 10.4,
      realizations: [
        { ipa: 'muwi', ortho: 'مووی', startSec: 10.1, endSec: 10.4 },
      ],
      selectedIdx: 0,
      realizationsSource: 'single',
    });
  });

  it('matches singleton concept intervals by key, not by sequential id', () => {
    const singletonConcept: Concept = {
      id: 5,
      key: 'concept-d',
      name: 'water',
      tag: 'untagged',
    };
    const record = makeRecord({
      concept: [{ start: 1, end: 2, text: 'water', concept_id: 'concept-d' }],
      ipa: [{ start: 1.1, end: 1.4, text: 'aw' }],
    });

    const form = buildSpeakerForm(record, singletonConcept, 'Fail01', {}, false, []);

    expect(form.utterances).toBe(1);
    expect(form.ipa).toBe('aw');
  });

  it('surfaces every IPA realization and defaults the canonical fields to realization A', () => {
    const record = makeRecord({
      concept: [{ start: 10, end: 14, text: 'hair', concept_id: 'hair' }],
      ipa: [
        { start: 10.1, end: 10.4, text: 'muwi' },
        { start: 11.1, end: 11.4, text: 'muː' },
        { start: 12.1, end: 12.4, text: 'moyi' },
      ],
      ortho_words: [
        { start: 10.15, end: 10.35, text: 'مووی' },
        { start: 11.15, end: 11.35, text: 'موو' },
        { start: 12.15, end: 12.35, text: 'مۆی' },
      ],
    });

    const form = buildSpeakerForm(record, concept, 'Fail02', {}, false, []);

    expect(form.realizations).toEqual([
      { ipa: 'muwi', ortho: 'مووی', startSec: 10.1, endSec: 10.4 },
      { ipa: 'muː', ortho: 'موو', startSec: 11.1, endSec: 11.4 },
      { ipa: 'moyi', ortho: 'مۆی', startSec: 12.1, endSec: 12.4 },
    ]);
    expect(form.selectedIdx).toBe(0);
    expect(form.variantCount).toBe(3);
    expect(form.utterances).toBe(3);
    expect(form.ipa).toBe('muwi');
    expect(form.ortho).toBe('مووی');
    expect(form.startSec).toBe(10.1);
    expect(form.endSec).toBe(10.4);
    expect(form.realizationsSource).toBe('auto-detect');
  });

  it('selects the canonical realization from manual overrides', () => {
    const record = makeRecord({
      concept: [{ start: 10, end: 14, text: 'hair', concept_id: 'hair' }],
      ipa: [
        { start: 10.1, end: 10.4, text: 'muwi' },
        { start: 11.1, end: 11.4, text: 'muː' },
      ],
      ortho_words: [
        { start: 10.15, end: 10.35, text: 'مووی' },
        { start: 11.15, end: 11.35, text: 'موو' },
      ],
    });

    const form = buildSpeakerForm(record, concept, 'Fail02', {
      manual_overrides: { canonical_realizations: { hair: { Fail02: 1 } } },
    }, false, []);

    expect(form.selectedIdx).toBe(1);
    expect(form.variantCount).toBe(2);
    expect(form.ipa).toBe('muː');
    expect(form.ortho).toBe('موو');
    expect(form.startSec).toBe(11.1);
    expect(form.endSec).toBe(11.4);
  });

  it('clamps stale canonical overrides to the last available realization', () => {
    const record = makeRecord({
      concept: [{ start: 10, end: 14, text: 'hair', concept_id: 'hair' }],
      ipa: [
        { start: 10.1, end: 10.4, text: 'muwi' },
        { start: 11.1, end: 11.4, text: 'muː' },
      ],
    });

    const form = buildSpeakerForm(record, concept, 'Fail02', {
      manual_overrides: { canonical_realizations: { hair: { Fail02: 5 } } },
    }, false, []);

    expect(form.selectedIdx).toBe(1);
    expect(form.ipa).toBe('muː');
  });

  it('coerces negative or non-integer canonical overrides to realization A', () => {
    const record = makeRecord({
      concept: [{ start: 10, end: 14, text: 'hair', concept_id: 'hair' }],
      ipa: [
        { start: 10.1, end: 10.4, text: 'muwi' },
        { start: 11.1, end: 11.4, text: 'muː' },
      ],
    });

    expect(buildSpeakerForm(record, concept, 'Fail02', {
      manual_overrides: { canonical_realizations: { hair: { Fail02: -1 } } },
    }, false, []).selectedIdx).toBe(0);
    expect(buildSpeakerForm(record, concept, 'Fail02', {
      manual_overrides: { canonical_realizations: { hair: { Fail02: 1.5 } } },
    }, false, []).selectedIdx).toBe(0);
  });

  it('prefers manual cognate overrides and per-speaker flags over automatic enrichments', () => {
    const record = makeRecord({
      concept: [{ start: 2, end: 2.4, text: 'hair', concept_id: 'hair' }],
      ipa: [{ start: 2.05, end: 2.3, text: 'muwi' }],
    });

    const enrichments = {
      cognate_sets: {
        hair: { B: ['Fail02'] },
      },
      manual_overrides: {
        cognate_sets: {
          hair: { A: ['Fail02'] },
        },
        speaker_flags: {
          hair: { Fail02: true },
        },
      },
    };

    const form = buildSpeakerForm(record, concept, 'Fail02', enrichments, false, ['ar']);
    expect(form.cognate).toBe('A');
    expect(form.flagged).toBe(true);
  });

  it('builds source-item variant realizations from the longest IPA interval under each sibling concept', () => {
    const sourceConcept: Concept = {
      id: 1,
      key: '2.15',
      name: 'brother of husband',
      tag: 'untagged',
      sourceItem: '2.15',
      variants: [
        { conceptKey: 'concept-a', conceptEn: 'brother of husband A', variantLabel: 'A' },
        { conceptKey: 'concept-b', conceptEn: 'brother of husband B', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'brother of husband A', concept_id: 'concept-a' },
        { start: 3, end: 6, text: 'brother of husband A', concept_id: 'concept-a' },
        { start: 7, end: 9, text: 'brother of husband B', concept_id: 'concept-b' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'bra-a-short' },
        { start: 3.1, end: 5.8, text: 'bra-a-long' },
        { start: 7.2, end: 8.4, text: 'bra-b' },
      ],
      ortho_words: [
        { start: 3.2, end: 5.7, text: 'برا ئا' },
        { start: 7.3, end: 8.3, text: 'برا ب' },
      ],
    });

    const form = buildSpeakerForm(record, sourceConcept, 'Fail02', {}, false, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.realizations).toEqual([
      { ipa: 'bra-a-long', ortho: 'برا ئا', startSec: 3.1, endSec: 5.8 },
      { ipa: 'bra-b', ortho: 'برا ب', startSec: 7.2, endSec: 8.4 },
    ]);
    expect(form.utterances).toBe(3);
    expect(form.variantCount).toBe(2);
    expect(form.selectedIdx).toBe(0);
    expect(form.ipa).toBe('bra-a-long');
  });

  it('reads source-item canonical overrides from the source_item key', () => {
    const sourceConcept: Concept = {
      id: 1,
      key: '2.15',
      name: 'brother of husband',
      tag: 'untagged',
      sourceItem: '2.15',
      variants: [
        { conceptKey: 'concept-a', conceptEn: 'brother of husband A', variantLabel: 'A' },
        { conceptKey: 'concept-b', conceptEn: 'brother of husband B', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'brother of husband A', concept_id: 'concept-a' },
        { start: 3, end: 4, text: 'brother of husband B', concept_id: 'concept-b' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'bra-a' },
        { start: 3.1, end: 3.4, text: 'bra-b' },
      ],
    });

    const form = buildSpeakerForm(record, sourceConcept, 'Fail02', {
      manual_overrides: { canonical_realizations: { '2.15': { Fail02: 1 } } },
    }, false, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.selectedIdx).toBe(1);
    expect(form.variantCount).toBe(2);
    expect(form.ipa).toBe('bra-b');
  });

  it('keeps empty source-item variant slots visible when a speaker is missing one sibling concept', () => {
    const sourceConcept: Concept = {
      id: 1,
      key: '2.15',
      name: 'brother of husband',
      tag: 'untagged',
      sourceItem: '2.15',
      variants: [
        { conceptKey: 'concept-a', conceptEn: 'brother of husband A', variantLabel: 'A' },
        { conceptKey: 'concept-b', conceptEn: 'brother of husband B', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [{ start: 1, end: 2, text: 'brother of husband A', concept_id: 'concept-a' }],
      ipa: [{ start: 1.1, end: 1.4, text: 'bra-a' }],
      ortho_words: [{ start: 1.15, end: 1.35, text: 'برا ئا' }],
    });

    const form = buildSpeakerForm(record, sourceConcept, 'Fail02', {}, false, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.realizations).toEqual([
      { ipa: 'bra-a', ortho: 'برا ئا', startSec: 1.1, endSec: 1.4 },
      { ipa: '', ortho: '', startSec: null, endSec: null },
    ]);
    expect(form.utterances).toBe(1);
    expect(form.variantCount).toBe(2);
  });

  it('collapses per-IPA auto-detection when the speaker dismiss flag is set', () => {
    const record = makeRecord({
      concept: [{ start: 10, end: 14, text: 'hair', concept_id: 'hair' }],
      ipa: [
        { start: 10.1, end: 10.4, text: 'muwi' },
        { start: 11.1, end: 12.4, text: 'muː-long' },
      ],
      ortho_words: [
        { start: 10.15, end: 10.35, text: 'مووی' },
        { start: 11.15, end: 12.35, text: 'موو' },
      ],
    });

    const form = buildSpeakerForm(record, concept, 'Fail02', {
      manual_overrides: { auto_detect_dismissed: { hair: { Fail02: true } } },
    }, false, []);

    expect(form.realizationsSource).toBe('single');
    expect(form.realizations).toEqual([
      { ipa: 'muː-long', ortho: 'موو', startSec: 11.1, endSec: 12.4 },
    ]);
    expect(form.utterances).toBe(2);
    expect(form.variantCount).toBe(1);
  });

  it('prioritizes source-item variants over per-concept auto-detect dismissal', () => {
    const sourceConcept: Concept = {
      id: 1,
      key: '2.15',
      name: 'brother of husband',
      tag: 'untagged',
      sourceItem: '2.15',
      variants: [
        { conceptKey: 'concept-a', conceptEn: 'brother of husband A', variantLabel: 'A' },
        { conceptKey: 'concept-b', conceptEn: 'brother of husband B', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'brother of husband A', concept_id: 'concept-a' },
        { start: 3, end: 4, text: 'brother of husband B', concept_id: 'concept-b' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'bra-a' },
        { start: 3.1, end: 3.4, text: 'bra-b' },
      ],
    });

    const form = buildSpeakerForm(record, sourceConcept, 'Fail02', {
      manual_overrides: { auto_detect_dismissed: { 'concept-a': { Fail02: true } } },
    }, false, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.realizations).toHaveLength(2);
  });

  it('preserves external flagged state and leaves timing empty when no concept interval matches', () => {
    const record = makeRecord({
      concept: [{ start: 4, end: 4.4, text: 'water' }],
      ipa: [{ start: 4.05, end: 4.2, text: 'aw' }],
    });

    const form = buildSpeakerForm(record, concept, 'Fail02', {}, true, ['ar']);
    expect(form.flagged).toBe(true);
    expect(form.startSec).toBeNull();
    expect(form.endSec).toBeNull();
    expect(form.ipa).toBe('');
    expect(form.utterances).toBe(0);
    expect(form.realizations).toEqual([]);
    expect(form.selectedIdx).toBe(0);
  });
});
