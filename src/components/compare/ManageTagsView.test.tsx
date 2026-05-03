// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

let mockStoreTags: Array<{ id: string; name: string; color: string; concepts: string[] }> = [];

vi.mock('../../stores/tagStore', () => ({
  useTagStore: (selector: (state: unknown) => unknown) => selector({
    tags: mockStoreTags,
  }),
}));

import { ManageTagsView } from './ManageTagsView';

type LingTag = { id: string; name: string; color: string; dotClass: string; count: number };
type Concept = {
  id: number;
  key: string;
  name: string;
  tag: 'untagged' | 'review' | 'confirmed' | 'problematic';
  sourceItem?: string;
  sourceSurvey?: string;
  customOrder?: number;
};

const baseTags: LingTag[] = [
  { id: 'review-needed', name: 'Review needed', color: '#f59e0b', dotClass: 'bg-amber-400', count: 2 },
  { id: 'confirmed', name: 'Confirmed', color: '#10b981', dotClass: 'bg-emerald-500', count: 1 },
];

const baseConcepts: Concept[] = [
  { id: 1, key: 'water', name: 'water', tag: 'untagged' },
  { id: 2, key: 'fire', name: 'fire', tag: 'review' },
  { id: 3, key: 'earth', name: 'earth', tag: 'confirmed' },
];

function renderManageTagsView(overrides: Partial<React.ComponentProps<typeof ManageTagsView>> = {}) {
  const props: React.ComponentProps<typeof ManageTagsView> = {
    tags: baseTags,
    concepts: baseConcepts,
    onCreateTag: vi.fn(),
    onUpdateTag: vi.fn(),
    tagSearch: '',
    setTagSearch: vi.fn(),
    newTagName: '',
    setNewTagName: vi.fn(),
    newTagColor: '#6366f1',
    setNewTagColor: vi.fn(),
    showUntagged: false,
    setShowUntagged: vi.fn(),
    selectedTagId: null,
    setSelectedTagId: vi.fn(),
    conceptSearch: '',
    setConceptSearch: vi.fn(),
    tagConcept: vi.fn(),
    untagConcept: vi.fn(),
    ...overrides,
  };

  return { ...render(<ManageTagsView {...props} />), props };
}

beforeEach(() => {
  mockStoreTags = [
    { id: 'review-needed', name: 'Review needed', color: '#f59e0b', concepts: ['fire'] },
    { id: 'confirmed', name: 'Confirmed', color: '#10b981', concepts: ['earth'] },
  ];
});

afterEach(() => {
  cleanup();
});

describe('ManageTagsView', () => {
  it('renders the tag creation controls and forwards creation inputs', () => {
    const setNewTagName = vi.fn();
    const setNewTagColor = vi.fn();
    const onCreateTag = vi.fn();

    renderManageTagsView({
      newTagName: 'Borrowing',
      setNewTagName,
      newTagColor: '#10b981',
      setNewTagColor,
      onCreateTag,
    });

    fireEvent.change(screen.getByPlaceholderText(/new tag name/i), { target: { value: 'Loanword' } });
    fireEvent.click(screen.getByLabelText('Select tag color #6366f1'));
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(setNewTagName).toHaveBeenCalledWith('Loanword');
    expect(setNewTagColor).toHaveBeenCalledWith('#6366f1');
    expect(onCreateTag).toHaveBeenCalledWith('Borrowing', '#10b981');
  });

  it('enters tag rename mode and saves the trimmed tag name', () => {
    const onUpdateTag = vi.fn();

    renderManageTagsView({
      selectedTagId: 'review-needed',
      onUpdateTag,
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Edit tag' })[0]);
    fireEvent.change(screen.getByLabelText('Rename tag'), { target: { value: '  Needs review  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save tag' }));

    expect(onUpdateTag).toHaveBeenCalledWith('review-needed', 'Needs review');
  });

  it('toggles concept assignment using the selected tag membership from the store', () => {
    const tagConcept = vi.fn();
    const untagConcept = vi.fn();

    renderManageTagsView({
      selectedTagId: 'review-needed',
      tagConcept,
      untagConcept,
    });

    fireEvent.click(screen.getByRole('button', { name: /fire/i }));
    fireEvent.click(screen.getByRole('button', { name: /water/i }));

    expect(untagConcept).toHaveBeenCalledWith('review-needed', 'fire');
    expect(tagConcept).toHaveBeenCalledWith('review-needed', 'water');
  });
});
