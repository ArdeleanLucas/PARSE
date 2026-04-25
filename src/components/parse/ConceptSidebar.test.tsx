// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { ConceptSidebar } from './ConceptSidebar';

const baseConcepts = [
  { id: 1, name: 'water', tag: 'untagged' as const },
  { id: 2, name: 'fire', tag: 'confirmed' as const, surveyItem: '2.1' },
];

const baseTags = [
  { id: 'review-needed', name: 'Review needed', color: '#f59e0b' },
];

afterEach(() => {
  cleanup();
});

describe('ConceptSidebar', () => {
  it('renders the provided concept list with the active concept highlighted', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="az"
        onSortModeChange={vi.fn()}
        hasSurveyItems
        filteredConcepts={baseConcepts}
        tagFilter="all"
        onTagFilterChange={vi.fn()}
        tags={baseTags}
        activeConceptId={2}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('2 concepts')).toBeTruthy();
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    const active = screen.getByRole('button', { name: /fire/i });
    expect(active.className).toContain('bg-indigo-50');
    expect(active.textContent ?? '').toContain('2');
  });

  it('forwards search and concept-selection callbacks', () => {
    const onQueryChange = vi.fn();
    const onConceptSelect = vi.fn();
    const onTagFilterChange = vi.fn();

    render(
      <ConceptSidebar
        query=""
        onQueryChange={onQueryChange}
        sortMode="survey"
        onSortModeChange={vi.fn()}
        hasSurveyItems
        filteredConcepts={baseConcepts}
        tagFilter="all"
        onTagFilterChange={onTagFilterChange}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={onConceptSelect}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/search concepts/i), { target: { value: 'fir' } });
    fireEvent.click(screen.getByTestId('tagfilter-unreviewed'));
    fireEvent.click(screen.getByRole('button', { name: /fire/i }));

    expect(onQueryChange).toHaveBeenCalledWith('fir');
    expect(onTagFilterChange).toHaveBeenCalledWith('unreviewed');
    expect(onConceptSelect).toHaveBeenCalledWith(2);
  });
});
