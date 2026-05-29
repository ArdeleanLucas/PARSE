import { describe, expect, it } from 'vitest';
import { buildElicitationDetailsByConceptKey } from './elicitationDetails';
import type { AnnotationRecord } from '../api/types';

function record(tiers: AnnotationRecord['tiers']): AnnotationRecord {
  return { version: 1, speaker: 'S', tiers } as unknown as AnnotationRecord;
}

describe('buildElicitationDetailsByConceptKey', () => {
  it('orders entries by interval start regardless of file order, and labels by that rank', () => {
    // File order is deliberately NOT start order: later start appears first.
    const out = buildElicitationDetailsByConceptKey(record({
      concept: {
        type: 'interval',
        intervals: [
          { start: 13350, end: 13351, text: 'rain', concept_id: '42', audition_prefix: '3.1' },
          { start: 5325, end: 5326, text: 'rain', concept_id: '42', audition_prefix: '126' },
        ],
      },
    } as unknown as AnnotationRecord['tiers']));

    expect(out['42'].map((d) => d.label)).toEqual(['A', 'B']);
    // A is the earliest by start (5325 → item 126), B the later (13350 → item 3.1).
    expect(out['42'][0].sourceItem).toBe('126');
    expect(out['42'][1].sourceItem).toBe('3.1');
  });

  it('attaches distinct overlapping IPA/ortho texts joined with " / "', () => {
    const out = buildElicitationDetailsByConceptKey(record({
      concept: { type: 'interval', intervals: [{ start: 5325, end: 5326, text: 'rain', concept_id: '42', audition_prefix: '126' }] },
      ipa: { type: 'interval', intervals: [
        { start: 5325, end: 5326, text: 'waran' },
        { start: 5325, end: 5326, text: 'waːraːn' },
        { start: 5325, end: 5326, text: 'waran' }, // duplicate collapses
        { start: 9999, end: 10000, text: 'noise' }, // non-overlapping ignored
      ] },
      ortho: { type: 'interval', intervals: [{ start: 5325, end: 5326, text: 'واران' }] },
    } as unknown as AnnotationRecord['tiers']));

    expect(out['42'][0].ipa).toBe('waran / waːraːn');
    expect(out['42'][0].ortho).toBe('واران');
  });

  it('labels a single interval with an empty string (no A/B noise)', () => {
    const out = buildElicitationDetailsByConceptKey(record({
      concept: { type: 'interval', intervals: [{ start: 1, end: 2, text: 'sun', concept_id: '7', audition_prefix: '9' }] },
    } as unknown as AnnotationRecord['tiers']));
    expect(out['7']).toHaveLength(1);
    expect(out['7'][0].label).toBe('');
  });

  it('skips intervals without a concept_id and tolerates a missing record', () => {
    const out = buildElicitationDetailsByConceptKey(record({
      concept: { type: 'interval', intervals: [{ start: 1, end: 2, text: 'x' }] },
    } as unknown as AnnotationRecord['tiers']));
    expect(out).toEqual({});
    expect(buildElicitationDetailsByConceptKey(null)).toEqual({});
    expect(buildElicitationDetailsByConceptKey(undefined)).toEqual({});
  });
});
