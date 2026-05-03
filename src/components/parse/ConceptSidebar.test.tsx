// @vitest-environment jsdom
import { useState } from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { ConceptSidebar, type ConceptStatusFilter } from './ConceptSidebar';

const baseConcepts = [
  { id: 1, name: 'water', tag: 'untagged' as const },
  { id: 2, name: 'fire', tag: 'confirmed' as const, sourceItem: '2.1' },
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
        hasSourceItems
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={2}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('2 concepts')).toBeTruthy();
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    const active = screen.getByRole('button', { name: /fire/i });
    expect(active.className).toContain('bg-indigo-50');
    expect(active.textContent ?? '').toContain('2.1');
  });

  it('forwards search, status filter, tag selection, and concept-selection callbacks', () => {
    const onQueryChange = vi.fn();
    const onConceptSelect = vi.fn();
    const onStatusFilterChange = vi.fn();
    const onTagSelectionChange = vi.fn();

    render(
      <ConceptSidebar
        query=""
        onQueryChange={onQueryChange}
        sortMode="survey"
        onSortModeChange={vi.fn()}
        hasSourceItems
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={onStatusFilterChange}
        selectedTagIds={new Set()}
        onTagSelectionChange={onTagSelectionChange}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={onConceptSelect}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText(/search concepts/i), { target: { value: 'fir' } });
    fireEvent.click(screen.getByTestId('tagfilter-unreviewed'));
    fireEvent.click(screen.getByRole('button', { name: /review needed/i }));
    fireEvent.click(screen.getByRole('button', { name: /fire/i }));

    expect(onQueryChange).toHaveBeenCalledWith('fir');
    expect(onStatusFilterChange).toHaveBeenCalledWith('unreviewed');
    expect(onTagSelectionChange).toHaveBeenCalledWith(new Set(['review-needed']));
    expect(onConceptSelect).toHaveBeenCalledWith(2);
  });

  it('allows multiple user tag chips to be selected and deselected independently', () => {
    function Harness() {
      const [statusFilter, setStatusFilter] = useState<ConceptStatusFilter>('all');
      const [selectedTagIds, setSelectedTagIds] = useState<Set<string>>(new Set(['review-needed']));
      return (
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortMode="az"
          onSortModeChange={vi.fn()}
          hasSourceItems
          filteredConcepts={baseConcepts}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          selectedTagIds={selectedTagIds}
          onTagSelectionChange={setSelectedTagIds}
          tags={[...baseTags, { id: 'semantic', name: 'Semantic', color: '#0f766e' }]}
          activeConceptId={1}
          onConceptSelect={vi.fn()}
        />
      );
    }

    render(<Harness />);

    const review = screen.getByRole('button', { name: /review needed/i });
    const semantic = screen.getByRole('button', { name: /semantic/i });
    expect(review.className).toContain('text-white');
    expect(semantic.className).not.toContain('text-white');

    fireEvent.click(semantic);
    expect(screen.getByRole('button', { name: /review needed/i }).className).toContain('text-white');
    expect(screen.getByRole('button', { name: /semantic/i }).className).toContain('text-white');

    fireEvent.click(screen.getByRole('button', { name: /review needed/i }));
    expect(screen.getByRole('button', { name: /review needed/i }).className).not.toContain('text-white');
    expect(screen.getByRole('button', { name: /semantic/i }).className).toContain('text-white');
  });

  it('keeps status filter chips single-select', () => {
    function Harness() {
      const [statusFilter, setStatusFilter] = useState<ConceptStatusFilter>('unreviewed');
      return (
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortMode="az"
          onSortModeChange={vi.fn()}
          hasSourceItems
          filteredConcepts={baseConcepts}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={baseTags}
          activeConceptId={1}
          onConceptSelect={vi.fn()}
        />
      );
    }

    render(<Harness />);
    fireEvent.click(screen.getByTestId('tagfilter-flagged'));

    expect(screen.getByTestId('tagfilter-flagged').className).toContain('bg-rose-500');
    expect(screen.getByTestId('tagfilter-unreviewed').className).not.toContain('bg-amber-500');
  });

  it('clears selected user tags when All is clicked', () => {
    function Harness() {
      const [statusFilter, setStatusFilter] = useState<ConceptStatusFilter>('flagged');
      const [selectedTagIds, setSelectedTagIds] = useState<Set<string>>(new Set(['review-needed']));
      return (
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortMode="az"
          onSortModeChange={vi.fn()}
          hasSourceItems
          filteredConcepts={baseConcepts}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          selectedTagIds={selectedTagIds}
          onTagSelectionChange={setSelectedTagIds}
          tags={baseTags}
          activeConceptId={1}
          onConceptSelect={vi.fn()}
        />
      );
    }

    render(<Harness />);
    expect(screen.getByRole('button', { name: /review needed/i }).className).toContain('text-white');
    expect(screen.getByTestId('tagfilter-flagged').className).toContain('bg-rose-500');

    fireEvent.click(screen.getByTestId('tagfilter-all'));

    expect(screen.getByTestId('tagfilter-all').className).toContain('bg-slate-600');
    expect(screen.getByRole('button', { name: /review needed/i }).className).not.toContain('text-white');
  });

  it('shows source survey plus source item as the concept badge when both are present', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="1n"
        onSortModeChange={vi.fn()}
        hasSourceItems
        filteredConcepts={[{ id: 42, name: 'forehead', tag: 'untagged' as const, sourceItem: '1.2', sourceSurvey: 'KLQ' }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={42}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /forehead/i }).textContent ?? '').toContain('KLQ 1.2');
  });

  it('shows bare source item as the concept badge without a prefix when source survey is absent', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="az"
        onSortModeChange={vi.fn()}
        hasSourceItems
        filteredConcepts={[{ id: 42, name: 'forehead', tag: 'untagged' as const, sourceItem: '1.2' }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={42}
        onConceptSelect={vi.fn()}
      />,
    );

    const text = screen.getByRole('button', { name: /forehead/i }).textContent ?? '';
    expect(text).toContain('1.2');
    expect(text).not.toContain('#1.2');
  });

  it('falls back to a #id badge when no source item is present', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="survey"
        onSortModeChange={vi.fn()}
        hasSourceItems={false}
        filteredConcepts={[{ id: 42, name: 'forehead', tag: 'untagged' as const }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={42}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /forehead/i }).textContent ?? '').toContain('#42');
  });

  it('labels the source-aware sort tab as Source', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="1n"
        onSortModeChange={vi.fn()}
        hasSourceItems
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('Source')).toBeTruthy();
    expect(screen.queryByText('Survey')).toBeNull();
  });

  it('renders mixed source and #id badges and enables Source sorting when any source item exists', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="1n"
        onSortModeChange={vi.fn()}
        hasSourceItems
        filteredConcepts={[
          { id: 42, name: 'forehead', tag: 'untagged' as const, sourceItem: '1.2', sourceSurvey: 'KLQ' },
          { id: 43, name: 'hair', tag: 'confirmed' as const },
        ]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={42}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /forehead/i }).textContent ?? '').toContain('KLQ 1.2');
    expect(screen.getByRole('button', { name: /hair/i }).textContent ?? '').toContain('#43');
    expect(screen.getByTestId('concept-sort-survey').hasAttribute('disabled')).toBe(false);
  });
});
