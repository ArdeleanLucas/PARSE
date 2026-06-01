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

    expect(buildSpeakerForm(record, concept, 'Fail02', enrichments, ['ar', 'fa'])).toEqual({
      speaker: 'Fail02',
      ipa: 'muwi',
      ortho: 'مووی',
      utterances: 1,
      variantCount: 1,
      similarityByLang: { ar: 0.9, fa: null },
      cognate: '—',
      cognateKey: 'hair',
      flagged: false,
      startSec: 10.1,
      endSec: 10.4,
      realizations: [
        { ipa: 'muwi', ortho: 'مووی', startSec: 10.1, endSec: 10.4 },
      ],
      selectedIdx: 0,
      realizationsSource: 'single',
      pastEndOfAudio: false,
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

    const form = buildSpeakerForm(record, singletonConcept, 'Fail01', {}, []);

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

    const form = buildSpeakerForm(record, concept, 'Fail02', {}, []);

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
    }, []);

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
    }, []);

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
    }, []).selectedIdx).toBe(0);
    expect(buildSpeakerForm(record, concept, 'Fail02', {
      manual_overrides: { canonical_realizations: { hair: { Fail02: 1.5 } } },
    }, []).selectedIdx).toBe(0);
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

    const form = buildSpeakerForm(record, concept, 'Fail02', enrichments, ['ar']);
    expect(form.cognate).toBe('A');
    expect(form.flagged).toBe(true);
  });

  it('flagged reflects only the per-speaker flag, so an explicit false clears it (MC-449-A)', () => {
    // Regression: the per-row Flag button toggles speaker_flags[concept][speaker].
    // Writing `false` must clear form.flagged regardless of any concept-level
    // "problematic" tag — otherwise the per-row flag is stuck amber forever.
    const record = makeRecord({
      concept: [{ start: 2, end: 2.4, text: 'hair', concept_id: 'hair' }],
      ipa: [{ start: 2.05, end: 2.3, text: 'muwi' }],
    });

    const flaggedOn = buildSpeakerForm(
      record,
      concept,
      'Fail02',
      { manual_overrides: { speaker_flags: { hair: { Fail02: true } } } },
      ['ar'],
    );
    expect(flaggedOn.flagged).toBe(true);

    const flaggedOff = buildSpeakerForm(
      record,
      concept,
      'Fail02',
      { manual_overrides: { speaker_flags: { hair: { Fail02: false } } } },
      ['ar'],
    );
    expect(flaggedOff.flagged).toBe(false);
  });


  it('reads grouped source-item cognate, flag, and similarity from the selected variant numeric key', () => {
    const groupedConcept: Concept = {
      id: 32,
      key: '1.1',
      name: 'hair',
      tag: 'untagged',
      sourceItem: '1.1',
      variants: [
        { conceptKey: '1', conceptEn: 'hair (A)', variantLabel: 'A' },
        { conceptKey: '599', conceptEn: 'hair (B)', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'hair (A)', concept_id: '1' },
        { start: 3, end: 4, text: 'hair (B)', concept_id: '599' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'mu-a' },
        { start: 3.1, end: 3.4, text: 'mu-b' },
      ],
    });

    const form = buildSpeakerForm(record, groupedConcept, 'Fail02', {
      cognate_sets: {
        '1.1': { Z: ['Fail02'] },
        '599': { A: ['Fail02'] },
      },
      similarity: {
        '1.1': { Fail02: { ar: { score: 0.01, has_reference_data: true } } },
        '599': { Fail02: { ar: { score: 0.88, has_reference_data: true } } },
      },
      manual_overrides: {
        canonical_realizations: { '1.1': { Fail02: 1 } },
        speaker_flags: {
          '1.1': { Fail02: false },
          '599': { Fail02: true },
        },
      },
    }, ['ar']);

    expect(form.selectedIdx).toBe(1);
    expect(form.cognateKey).toBe('599');
    expect(form.cognate).toBe('A');
    expect(form.flagged).toBe(true);
    expect(form.similarityByLang.ar).toBe(0.88);
  });

  it('reads merged cognate and flag from the selected merged numeric key', () => {
    const mergedConcept: Concept = { id: 1, key: '527', name: 'head', tag: 'untagged', mergedKeys: ['527', '247', '248'] };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'head', concept_id: '527' },
        { start: 3, end: 4, text: 'head A', concept_id: '247' },
        { start: 5, end: 6, text: 'head B', concept_id: '248' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'sar' },
        { start: 3.1, end: 3.4, text: 'sar-a' },
        { start: 5.1, end: 5.4, text: 'sar-b' },
      ],
    });

    const form = buildSpeakerForm(record, mergedConcept, 'Fail02', {
      cognate_sets: {
        '527': { C: ['Fail02'] },
        '248': { B: ['Fail02'] },
      },
      manual_overrides: {
        canonical_realizations: { '527': { Fail02: 2 } },
        speaker_flags: {
          '527': { Fail02: false },
          '248': { Fail02: true },
        },
      },
    }, []);

    expect(form.selectedIdx).toBe(2);
    expect(form.cognateKey).toBe('248');
    expect(form.cognate).toBe('B');
    expect(form.flagged).toBe(true);
  });

  it('keeps singleton cognate and flag keying unchanged', () => {
    const singletonConcept: Concept = { id: 527, key: '527', name: 'head', tag: 'untagged' };
    const record = makeRecord({
      concept: [{ start: 1, end: 2, text: 'head', concept_id: '527' }],
      ipa: [{ start: 1.1, end: 1.4, text: 'sar' }],
    });

    const form = buildSpeakerForm(record, singletonConcept, 'Fail02', {
      cognate_sets: { '527': { D: ['Fail02'] } },
      manual_overrides: { speaker_flags: { '527': { Fail02: true } } },
    }, []);

    expect(form.cognateKey).toBe('527');
    expect(form.cognate).toBe('D');
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

    const form = buildSpeakerForm(record, sourceConcept, 'Fail02', {}, []);

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

  it('reads source-item canonical overrides from the concept key', () => {
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
    }, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.selectedIdx).toBe(1);
    expect(form.variantCount).toBe(2);
    expect(form.ipa).toBe('bra-b');
  });

  it('isolates source-item canonical overrides for survey-qualified grouped keys', () => {
    const sourceConcept: Concept = {
      id: 1,
      key: 'source:EXT:5.1',
      name: 'The boy cut the rope with a knife',
      tag: 'untagged',
      sourceItem: '5.1',
      sourceSurvey: 'EXT',
      variants: [
        { conceptKey: '563', conceptEn: 'The boy cut the rope with a knife !', variantLabel: 'A' },
        { conceptKey: '596', conceptEn: 'The boy cut the rope with a knife', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'The boy cut the rope with a knife !', concept_id: '563' },
        { start: 3, end: 4, text: 'The boy cut the rope with a knife', concept_id: '596' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'clause-a' },
        { start: 3.1, end: 3.4, text: 'clause-b' },
      ],
    });

    const form = buildSpeakerForm(record, sourceConcept, 'Saha01', {
      manual_overrides: {
        canonical_realizations: {
          '5.1': { Saha01: 0 },
          'source:EXT:5.1': { Saha01: 1 },
        },
      },
    }, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.selectedIdx).toBe(1);
    expect(form.ipa).toBe('clause-b');
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

    const form = buildSpeakerForm(record, sourceConcept, 'Fail02', {}, []);

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
    }, []);

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
    }, []);

    expect(form.realizationsSource).toBe('source-item');
    expect(form.realizations).toHaveLength(2);
  });

  it('reflects the per-speaker flag and leaves timing empty when no concept interval matches', () => {
    const record = makeRecord({
      concept: [{ start: 4, end: 4.4, text: 'water' }],
      ipa: [{ start: 4.05, end: 4.2, text: 'aw' }],
    });

    const form = buildSpeakerForm(
      record,
      concept,
      'Fail02',
      { manual_overrides: { speaker_flags: { hair: { Fail02: true } } } },
      ['ar'],
    );
    expect(form.flagged).toBe(true);
    expect(form.startSec).toBeNull();
    expect(form.endSec).toBeNull();
    expect(form.ipa).toBe('');
    expect(form.utterances).toBe(0);
    expect(form.realizations).toEqual([]);
    expect(form.selectedIdx).toBe(0);
  });

  it('builds merged concept realizations from every merged key and marks the source as merged', () => {
    const mergedConcept: Concept = { id: 1, key: '527', name: 'head', tag: 'untagged', mergedKeys: ['527', '247', '248'] };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'head', concept_id: '527' },
        { start: 3, end: 4, text: 'head (A)', concept_id: '247' },
        { start: 5, end: 6, text: 'head (B)', concept_id: '248' },
        { start: 7, end: 9, text: 'head (B)', concept_id: '248' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'sar' },
        { start: 3.1, end: 3.4, text: 'sar-a' },
        { start: 5.1, end: 5.4, text: 'sar-b-short' },
        { start: 7.1, end: 8.8, text: 'sar-b-long' },
      ],
      ortho_words: [
        { start: 1.15, end: 1.35, text: 'سەر' },
        { start: 3.15, end: 3.35, text: 'سەر ئا' },
        { start: 7.15, end: 8.7, text: 'سەر ب' },
      ],
    });

    const form = buildSpeakerForm(record, mergedConcept, 'Fail02', {}, []);

    expect(form.realizationsSource).toBe('merged');
    expect(form.realizations).toEqual([
      { ipa: 'sar', ortho: 'سەر', startSec: 1.1, endSec: 1.4 },
      { ipa: 'sar-a', ortho: 'سەر ئا', startSec: 3.1, endSec: 3.4 },
      { ipa: 'sar-b-long', ortho: 'سەر ب', startSec: 7.1, endSec: 8.8 },
    ]);
    expect(form.utterances).toBe(4);
    expect(form.variantCount).toBe(3);
    expect(form.ipa).toBe('sar');
  });

  it('uses the merged primary key for canonical realization overrides', () => {
    const mergedConcept: Concept = { id: 1, key: '527', name: 'head', tag: 'untagged', mergedKeys: ['527', '247', '248'] };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'head', concept_id: '527' },
        { start: 3, end: 4, text: 'head (A)', concept_id: '247' },
        { start: 5, end: 6, text: 'head (B)', concept_id: '248' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'sar' },
        { start: 3.1, end: 3.4, text: 'sar-a' },
        { start: 5.1, end: 5.4, text: 'sar-b' },
      ],
    });

    const form = buildSpeakerForm(record, mergedConcept, 'Fail02', {
      manual_overrides: { canonical_realizations: { '527': { Fail02: 2 } } },
    }, []);

    expect(form.realizationsSource).toBe('merged');
    expect(form.selectedIdx).toBe(2);
    expect(form.ipa).toBe('sar-b');
  });

  it('keeps empty merged realization slots visible when a speaker lacks absorbed-key IPA', () => {
    const mergedConcept: Concept = { id: 1, key: '527', name: 'head', tag: 'untagged', mergedKeys: ['527', '247', '248'] };
    const record = makeRecord({
      concept: [{ start: 1, end: 2, text: 'head', concept_id: '527' }],
      ipa: [{ start: 1.1, end: 1.4, text: 'sar' }],
    });

    const form = buildSpeakerForm(record, mergedConcept, 'Fail02', {}, []);

    expect(form.realizationsSource).toBe('merged');
    expect(form.realizations).toEqual([
      { ipa: 'sar', ortho: '', startSec: 1.1, endSec: 1.4 },
      { ipa: '', ortho: '', startSec: null, endSec: null },
      { ipa: '', ortho: '', startSec: null, endSec: null },
    ]);
  });

  it('matches utterance intervals tagged with any merged key', () => {
    const mergedConcept: Concept = { id: 1, key: '527', name: 'head', tag: 'untagged', mergedKeys: ['527', '247'] };
    const record = makeRecord({
      concept: [{ start: 3, end: 4, text: 'head (A)', concept_id: '247' }],
      ipa: [{ start: 3.1, end: 3.4, text: 'sar-a' }],
    });

    const form = buildSpeakerForm(record, mergedConcept, 'Fail02', {}, []);

    expect(form.utterances).toBe(1);
    expect(form.ipa).toBe('');
    expect(form.realizations[1]).toEqual({ ipa: 'sar-a', ortho: '', startSec: 3.1, endSec: 3.4 });
  });

  it('uses the merged branch before source-item branch when both are present', () => {
    const mergedSourceConcept: Concept = {
      id: 1,
      key: '2.47',
      name: 'head',
      tag: 'untagged',
      sourceItem: '2.47',
      variants: [
        { conceptKey: '247', conceptEn: 'head A', variantLabel: 'A' },
        { conceptKey: '248', conceptEn: 'head B', variantLabel: 'B' },
      ],
      mergedKeys: ['247', '248', '527'],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'head A', concept_id: '247' },
        { start: 3, end: 4, text: 'head B', concept_id: '248' },
        { start: 5, end: 6, text: 'head', concept_id: '527' },
      ],
      ipa: [
        { start: 1.1, end: 1.4, text: 'sar-a' },
        { start: 3.1, end: 3.4, text: 'sar-b' },
        { start: 5.1, end: 5.4, text: 'sar-bare' },
      ],
    });

    const form = buildSpeakerForm(record, mergedSourceConcept, 'Fail02', {}, []);

    expect(form.realizationsSource).toBe('merged');
    expect(form.realizations).toHaveLength(3);
    expect(form.realizations[2].ipa).toBe('sar-bare');
  });

  describe('pastEndOfAudio', () => {
    const concept: Concept = { id: 1, key: 'hair', name: 'Hair', tag: 'untagged' };

    function makeRecordWithDuration(duration: number | undefined, ipa: AnnotationInterval[], conceptIv: AnnotationInterval[]): AnnotationRecord {
      const record = makeRecord({ ipa, concept: conceptIv });
      // source_audio_duration_sec lives on AnnotationRecord directly.
      (record as AnnotationRecord & { source_audio_duration_sec?: number }).source_audio_duration_sec = duration;
      return record;
    }

    it('is false when source_audio_duration_sec is missing', () => {
      const record = makeRecord({
        concept: [{ start: 100, end: 101, text: 'hair', concept_id: 'hair' }],
        ipa: [{ start: 100, end: 101, text: 'mu' }],
      });
      const form = buildSpeakerForm(record, concept, 'Fail02', {}, []);
      expect(form.pastEndOfAudio).toBe(false);
    });

    it('is false when realization start sits inside the working WAV', () => {
      const record = makeRecordWithDuration(8590,
        [{ start: 8000, end: 8001, text: 'mu' }],
        [{ start: 8000, end: 8001, text: 'hair', concept_id: 'hair' }]);
      const form = buildSpeakerForm(record, concept, 'Khan02', {}, []);
      expect(form.startSec).toBe(8000);
      expect(form.pastEndOfAudio).toBe(false);
    });

    it('is true when realization start is past source_audio_duration_sec (Khan01 manifest case)', () => {
      const record = makeRecordWithDuration(8590,
        [{ start: 12000, end: 12001, text: 'mu' }],
        [{ start: 12000, end: 12001, text: 'hair', concept_id: 'hair' }]);
      const form = buildSpeakerForm(record, concept, 'Khan01', {}, []);
      expect(form.startSec).toBe(12000);
      expect(form.pastEndOfAudio).toBe(true);
    });

    it('is true when realization end exceeds source_audio_duration_sec even if start is within', () => {
      const record = makeRecordWithDuration(8590,
        [{ start: 8589, end: 8591, text: 'mu' }],
        [{ start: 8589, end: 8591, text: 'hair', concept_id: 'hair' }]);
      const form = buildSpeakerForm(record, concept, 'Khan01', {}, []);
      expect(form.pastEndOfAudio).toBe(true);
    });

    it('is true when realization start equals source_audio_duration_sec (no playable audio left)', () => {
      const record = makeRecordWithDuration(8590,
        [{ start: 8590, end: 8590.5, text: 'mu' }],
        [{ start: 8590, end: 8590.5, text: 'hair', concept_id: 'hair' }]);
      const form = buildSpeakerForm(record, concept, 'Khan01', {}, []);
      expect(form.pastEndOfAudio).toBe(true);
    });

    it('is false when there is no matching realization (no canonical to flag)', () => {
      const record = makeRecordWithDuration(8590, [], []);
      const form = buildSpeakerForm(record, concept, 'Empty', {}, []);
      expect(form.startSec).toBeNull();
      expect(form.pastEndOfAudio).toBe(false);
    });
  });

  it('uses the focused interval index for same-concept elicitations and falls back per speaker', () => {
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'head', concept_id: '527' },
        { start: 3, end: 4, text: 'head', concept_id: '527' },
        { start: 5, end: 6, text: 'head', concept_id: '527' },
      ],
      ipa: [
        { start: 1, end: 2, text: 'sar' },
        { start: 3, end: 4, text: 'kapul' },
        { start: 5, end: 6, text: 'kapul-dup' },
      ],
      ortho_words: [
        { start: 1, end: 2, text: 'سەر' },
        { start: 3, end: 4, text: 'کەپول' },
        { start: 5, end: 6, text: 'کەپول٢' },
      ],
    });
    const head: Concept = { id: 527, key: '527', name: 'head', tag: 'untagged' };

    const oneIntervalRecord = makeRecord({
      concept: [{ start: 9, end: 10, text: 'head', concept_id: '527' }],
      ipa: [{ start: 9, end: 10, text: 'saha-first' }],
      ortho_words: [{ start: 9, end: 10, text: 'سەر' }],
    });

    expect(buildSpeakerForm(record, head, 'Fail01', {}, [], '527', 1).ipa).toBe('kapul');
    expect(buildSpeakerForm(record, head, 'Fail01', {}, [], '527', 2).ortho).toBe('کەپول٢');
    expect(buildSpeakerForm(record, head, 'Fail01', {}, [], '527', 99).ipa).toBe('sar');
    expect(buildSpeakerForm(oneIntervalRecord, head, 'Saha01', {}, [], '527', 2).ipa).toBe('saha-first');
  });

  it('uses the focused grouped variant key for source-item variants', () => {
    const sourceConcept: Concept = {
      id: 31,
      key: '31',
      name: 'head',
      tag: 'untagged',
      sourceItem: '31',
      variants: [
        { conceptKey: '247', conceptEn: 'head (A)', variantLabel: 'A' },
        { conceptKey: '527', conceptEn: 'head', variantLabel: 'B' },
      ],
    };
    const record = makeRecord({
      concept: [
        { start: 1, end: 2, text: 'head (A)', concept_id: '247' },
        { start: 3, end: 4, text: 'head', concept_id: '527' },
      ],
      ipa: [
        { start: 1, end: 2, text: 'sar-a' },
        { start: 3, end: 4, text: 'sar-b' },
      ],
    });

    expect(buildSpeakerForm(record, sourceConcept, 'Fail01', {}, [], '527', 0).ipa).toBe('sar-b');
    expect(buildSpeakerForm(record, sourceConcept, 'Fail01', {}, [], 'missing', 0).ipa).toBe('sar-a');
  });

});
