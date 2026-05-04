// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { AnnotationRecord } from '../../api/types';

let mockStoreTags: Array<{ id: string; label: string; color: string }> = [];
let mockSelectedSpeakers: string[] = [];
let mockConfigSpeakers: string[] = [];
let mockRecords: Record<string, AnnotationRecord> = {};
const mockSetConceptTag = vi.fn();
const mockClearConceptTag = vi.fn();

vi.mock('../../stores/tagStore', () => ({
  useTagStore: (selector: (state: unknown) => unknown) => selector({
    tags: mockStoreTags,
  }),
}));

vi.mock('../../stores/uiStore', () => ({
  useUIStore: (selector: (state: unknown) => unknown) => selector({ selectedSpeakers: mockSelectedSpeakers }),
}));

vi.mock('../../stores/configStore', () => ({
  useConfigStore: (selector: (state: unknown) => unknown) => selector({ config: { speakers: mockConfigSpeakers } }),
}));

vi.mock('../../stores/annotationStore', () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) => selector({
    records: mockRecords,
    setConceptTag: mockSetConceptTag,
    clearConceptTag: mockClearConceptTag,
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

function makeRecord(speaker: string, conceptTags: Record<string, string[]> = {}): AnnotationRecord {
  return {
    speaker,
    source_wav: `${speaker}.wav`,
    source_audio: `${speaker}.wav`,
    tiers: { concept: { name: 'concept', display_order: 0, intervals: [] } },
    concept_tags: conceptTags,
  };
}

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
    ...overrides,
  };

  return { ...render(<ManageTagsView {...props} />), props };
}

beforeEach(() => {
  mockStoreTags = [
    { id: 'review-needed', label: 'Review needed', color: '#f59e0b' },
    { id: 'confirmed', label: 'Confirmed', color: '#10b981' },
  ];
  mockSelectedSpeakers = ['S1'];
  mockConfigSpeakers = ['S1', 'S2'];
  mockRecords = {
    S1: makeRecord('S1', { fire: ['review-needed'] }),
    S2: makeRecord('S2', { water: ['review-needed'] }),
  };
  mockSetConceptTag.mockClear();
  mockClearConceptTag.mockClear();
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

  it('shows tag membership derived from selected speaker annotation records', () => {
    renderManageTagsView({ selectedTagId: 'review-needed' });

    expect(screen.getByRole('button', { name: /fire/i }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: /water/i }).getAttribute('aria-pressed')).toBe('false');
  });

  it('toggles concept assignment using the selected tag membership', () => {
    renderManageTagsView({ selectedTagId: 'review-needed' });

    fireEvent.click(screen.getByRole('button', { name: /water/i }));
    expect(mockSetConceptTag).toHaveBeenCalledWith('S1', 'water', 'review-needed');

    fireEvent.click(screen.getByRole('button', { name: /fire/i }));
    expect(mockClearConceptTag).toHaveBeenCalledWith('S1', 'fire', 'review-needed');
  });

  it('falls back to configured speakers when toggling with no selected speakers', () => {
    mockSelectedSpeakers = [];
    renderManageTagsView({ selectedTagId: 'confirmed' });

    fireEvent.click(screen.getByRole('button', { name: /earth/i }));

    expect(mockSetConceptTag).toHaveBeenCalledWith('S1', 'earth', 'confirmed');
    expect(mockSetConceptTag).toHaveBeenCalledWith('S2', 'earth', 'confirmed');
  });
});
