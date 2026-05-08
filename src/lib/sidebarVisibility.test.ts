import { describe, expect, it, vi } from 'vitest';
import { isConceptVariantVisibleInSidebar } from './sidebarVisibility';

const baseOptions = {
  scopedToSpeaker: false,
  activeSpeakerForSidebar: null,
  elicitedConceptKeys: new Set<string>(),
  selectedTagIds: new Set<string>(),
  getTagsForConcept: vi.fn(() => []),
  activeTagScope: undefined,
};

describe('isConceptVariantVisibleInSidebar', () => {
  it('hides variants outside the active speaker elicited concept set when scoped', () => {
    expect(isConceptVariantVisibleInSidebar({}, { conceptKey: '599' }, {
      ...baseOptions,
      scopedToSpeaker: true,
      activeSpeakerForSidebar: 'Saha01',
      elicitedConceptKeys: new Set(['1']),
    })).toBe(false);
  });

  it('requires every selected tag to be attached to the same variant key', () => {
    const getTagsForConcept = vi.fn((key: string) => key === '1'
      ? [{ id: 'custom-sk-concept-list' }, { id: 'confirmed' }]
      : [{ id: 'custom-sk-concept-list' }]);

    expect(isConceptVariantVisibleInSidebar({}, { conceptKey: '1' }, {
      ...baseOptions,
      selectedTagIds: new Set(['custom-sk-concept-list', 'confirmed']),
      getTagsForConcept,
      activeTagScope: ['Saha01'],
    })).toBe(true);
    expect(isConceptVariantVisibleInSidebar({}, { conceptKey: '599' }, {
      ...baseOptions,
      selectedTagIds: new Set(['custom-sk-concept-list', 'confirmed']),
      getTagsForConcept,
      activeTagScope: ['Saha01'],
    })).toBe(false);
    expect(getTagsForConcept).toHaveBeenCalledWith('1', ['Saha01']);
  });

  it('keeps variants visible by default when no speaker scope or tag filter rejects them', () => {
    expect(isConceptVariantVisibleInSidebar({}, { conceptKey: '1' }, baseOptions)).toBe(true);
  });
});
