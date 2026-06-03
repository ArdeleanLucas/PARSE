import { describe, it, expect } from 'vitest';
import { noteKeysForConcept } from '../speakerElicitedConcepts';

describe('noteKeysForConcept', () => {
  it('leads with the concept uid for identity concepts (so uid-keyed notes resolve)', () => {
    // Notes are uid-keyed post MC-458-E; the uid (concept.key) must come first
    // so resolveServerNote returns the current uid-keyed note, not a stale
    // localStorage/legacy fallback under the member csv id.
    expect(noteKeysForConcept({ key: 'c-311', variants: [{ conceptKey: '311' }] }))
      .toEqual(['c-311', '311']);
  });

  it('regression: grouped concept leads with the uid, not the member id (cold-under-cloud)', () => {
    // The old "variant csv ids only" form returned ['328'], which missed the
    // uid-keyed note (c-328) and fell back to a stale cached note.
    const keys = noteKeysForConcept({ key: 'c-328', variants: [{ conceptKey: '328' }] });
    expect(keys[0]).toBe('c-328');
    expect(keys).toContain('328');
  });

  it('includes every member of a multi-member concept after the uid', () => {
    expect(noteKeysForConcept({ key: 'c-1', variants: [{ conceptKey: '1' }, { conceptKey: '249' }, { conceptKey: '250' }] }))
      .toEqual(['c-1', '1', '249', '250']);
  });

  it('handles mergedKeys concepts', () => {
    expect(noteKeysForConcept({ key: 'c-527', mergedKeys: ['527', '247', '248'] }))
      .toEqual(['c-527', '527', '247', '248']);
  });

  it('singleton with no variants returns just its key', () => {
    expect(noteKeysForConcept({ key: '538' })).toEqual(['538']);
  });

  it('dedupes when the key equals a member id', () => {
    expect(noteKeysForConcept({ key: '538', variants: [{ conceptKey: '538' }] })).toEqual(['538']);
  });
});
