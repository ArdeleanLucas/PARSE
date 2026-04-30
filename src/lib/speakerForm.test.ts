import { describe, expect, it } from 'vitest';
import type { AnnotationInterval, AnnotationRecord } from '../api/types';
import { buildSpeakerForm } from './speakerForm';

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
      concept: [{ start: 10, end: 10.5, text: 'hair', concept_id: '1' }],
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
      similarityByLang: { ar: 0.9, fa: null },
      cognate: '—',
      flagged: false,
      startSec: 10,
      endSec: 10.5,
    });
  });

  it('prefers manual cognate overrides and per-speaker flags over automatic enrichments', () => {
    const record = makeRecord({
      concept: [{ start: 2, end: 2.4, text: 'hair', concept_id: '1' }],
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
  });
});
