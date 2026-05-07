import { describe, expect, it } from 'vitest';
import type { AnnotationRecord } from '../api/types';
import { speakerElicitedConceptKeys } from './speakerElicitedConcepts';

describe('speakerElicitedConceptKeys', () => {
  it('returns de-duplicated concept_id values from the concept tier', () => {
    const record: AnnotationRecord = {
      speaker: 'Fail02',
      tiers: {
        concept: {
          name: 'concept',
          display_order: 1,
          intervals: [
            { start: 0, end: 1, text: 'water', concept_id: '1' },
            { start: 2, end: 3, text: 'water again', concept_id: '1' },
            { start: 4, end: 5, text: 'fire', concept_id: '2' },
            { start: 6, end: 7, text: 'missing id' },
          ],
        },
      },
    };

    expect(Array.from(speakerElicitedConceptKeys(record)).sort()).toEqual(['1', '2']);
  });

  it('returns an empty set when the record or concept tier is missing', () => {
    expect(speakerElicitedConceptKeys(null).size).toBe(0);
    expect(speakerElicitedConceptKeys(undefined).size).toBe(0);
    expect(speakerElicitedConceptKeys({ speaker: 'Fail02', tiers: {} }).size).toBe(0);
  });
});
