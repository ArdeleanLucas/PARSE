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


  it('keeps singleton rows to one parent affordance and selects the singleton parent key', () => {
    const onConceptSelect = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{ id: 11, key: 'single-11', name: 'water', tag: 'confirmed' as const, sourceItem: '11' }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={11}
        activeConceptKey="single-11"
        onConceptSelect={onConceptSelect}
      />,
    );

    const row = screen.getByTestId('concept-row-11');
    const parentButton = screen.getByTestId('concept-parent-button-11');
    expect(row.querySelector('.flex.items-center')?.firstElementChild).toBe(parentButton);
    expect(row.querySelectorAll('button[data-testid^="concept-"]')).toHaveLength(1);
    expect(row.querySelector('[data-testid^="concept-variant-pill-"]')).toBeNull();

    fireEvent.click(parentButton);
    expect(onConceptSelect).toHaveBeenCalledWith(11, 'single-11');
  });

  it('renders two grouped variants as flat pills with distinct per-variant tag dots', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 79,
          key: 'source:JBIL:79',
          name: 'dog',
          tag: 'problematic' as const,
          sourceItem: '79',
          sourceSurvey: 'JBIL',
          variants: [
            { conceptKey: '298', conceptEn: 'dog (A)', variantLabel: 'A', tag: 'confirmed' as const },
            { conceptKey: '628', conceptEn: 'dog (B)', variantLabel: 'B', tag: 'problematic' as const },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={79}
        activeConceptKey="298"
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId('concept-parent-button-79').textContent ?? '').toContain('dog');
    expect(screen.getByTestId('concept-variant-pill-298').textContent ?? '').toContain('A');
    expect(screen.getByTestId('concept-variant-pill-628').textContent ?? '').toContain('B');
    expect(screen.getByTestId('concept-variant-pill-dot-298').className).toContain('bg-emerald-500');
    expect(screen.getByTestId('concept-variant-pill-dot-628').className).toContain('bg-rose-500');
  });

  it('suppresses the variant pill strip when hideVariantPills is true (compare-mode flood guard)', () => {
    const onConceptSelect = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 79,
          key: 'source:JBIL:79',
          name: 'dog',
          tag: 'problematic' as const,
          sourceItem: '79',
          sourceSurvey: 'JBIL',
          variants: [
            { conceptKey: '298', conceptEn: 'dog (A)', variantLabel: 'A', tag: 'confirmed' as const },
            { conceptKey: '628', conceptEn: 'dog (B)', variantLabel: 'B', tag: 'problematic' as const },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={79}
        activeConceptKey="298"
        onConceptSelect={onConceptSelect}
        hideVariantPills
      />,
    );

    expect(screen.queryByTestId('concept-variant-pill-298')).toBeNull();
    expect(screen.queryByTestId('concept-variant-pill-628')).toBeNull();
    const parentLabel = screen.getByTestId('concept-parent-button-79').getAttribute('aria-label') ?? '';
    expect(parentLabel.toLowerCase()).not.toContain('variants a b');

    fireEvent.click(screen.getByTestId('concept-parent-button-79'));
    expect(onConceptSelect).toHaveBeenCalledWith(79, '298');
  });

  it("clicking flat variant B selects variant B's conceptKey instead of the parent group key", () => {
    const onConceptSelect = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 79,
          key: 'source:JBIL:79',
          name: 'dog',
          tag: 'problematic' as const,
          sourceItem: '79',
          sourceSurvey: 'JBIL',
          variants: [
            { conceptKey: '298', conceptEn: 'dog (A)', variantLabel: 'A', tag: 'confirmed' as const },
            { conceptKey: '628', conceptEn: 'dog (B)', variantLabel: 'B', tag: 'problematic' as const },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={79}
        activeConceptKey="298"
        onConceptSelect={onConceptSelect}
      />,
    );

    fireEvent.click(screen.getByTestId('concept-variant-pill-628'));

    expect(onConceptSelect).toHaveBeenCalledWith(79, '628');
    expect(onConceptSelect).not.toHaveBeenCalledWith(79, 'source:JBIL:79');
  });

  it('renders the action feedback banner when actionFeedback prop is set', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        actionFeedback={{ message: 'Action failed', variant: 'error' }}
        onDismissActionFeedback={vi.fn()}
      />,
    );

    const banner = screen.getByTestId('sidebar-action-feedback');
    expect(banner.textContent ?? '').toContain('Action failed');
    expect(banner.className).toContain('bg-rose-50');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('does not render the action feedback banner when actionFeedback is null', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        actionFeedback={null}
      />,
    );

    expect(screen.queryByTestId('sidebar-action-feedback')).toBeNull();
  });

  it('clicking the action feedback dismiss button calls onDismissActionFeedback', () => {
    const onDismissActionFeedback = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        actionFeedback={{ message: 'Already exists', variant: 'warning' }}
        onDismissActionFeedback={onDismissActionFeedback}
      />,
    );

    const banner = screen.getByTestId('sidebar-action-feedback');
    expect(banner.className).toContain('bg-amber-50');
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismissActionFeedback).toHaveBeenCalledOnce();
  });

  it('renders Concept and Source parent pills with only the active sub-row visible', () => {
    const onSortParentChange = vi.fn();
    const { rerender } = render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={onSortParentChange}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail01"
      />,
    );

    expect(screen.getByTestId('concept-sort-parent-concept').className).toContain('bg-white');
    expect(screen.getByTestId('concept-sort-1n')).toBeTruthy();
    expect(screen.queryByTestId('concept-sort-source-time')).toBeNull();

    fireEvent.click(screen.getByTestId('concept-sort-parent-source'));
    expect(onSortParentChange).toHaveBeenCalledWith('source');

    rerender(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={onSortParentChange}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail01"
      />,
    );
    expect(screen.queryByTestId('concept-sort-1n')).toBeNull();
    expect(screen.getByTestId('concept-sort-source-time').className).toContain('bg-sky-600');
    expect(screen.getByText('Fail01')).toBeTruthy();
  });

  it('marks active and inactive sort toggles with data-toggle-state', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail01"
      />,
    );

    expect(screen.getByTestId('concept-sort-parent-concept').getAttribute('data-toggle-state')).toBe('off');
    expect(screen.getByTestId('concept-sort-parent-source').getAttribute('data-toggle-state')).toBe('on');
    expect(screen.getByTestId('concept-sort-source-time').getAttribute('data-toggle-state')).toBe('on');
    expect(screen.getByTestId('concept-sort-source-row').getAttribute('data-toggle-state')).toBe('off');
  });

  it('keeps Source disabled as a no-op until exactly one speaker is selected', () => {
    const onSortParentChange = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="row"
        onSortParentChange={onSortParentChange}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={baseTags}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
      />,
    );

    const source = screen.getByTestId('concept-sort-parent-source');
    expect(source.getAttribute('aria-disabled')).toBe('true');
    expect(source.title).toBe('Select one speaker to enable Source ordering');
    fireEvent.click(source);
    expect(onSortParentChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('concept-sort-az').className).toContain('bg-white');
  });

  it('renders source-item variant dots from each variant tag instead of the parent rollup', async () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 42,
          key: 'hair',
          name: 'hair',
          tag: 'problematic' as const,
          variants: [
            { conceptKey: 'hair-a', conceptEn: 'hair (A)', variantLabel: 'A', tag: 'untagged' as const },
            { conceptKey: 'hair-c', conceptEn: 'hair (C)', variantLabel: 'C', tag: 'problematic' as const },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={42}
        activeConceptKey="hair-a"
        onConceptSelect={vi.fn()}
      />,
    );

    const parentDot = screen.getByTestId('concept-parent-button-42').querySelector('span');
    await screen.findByTestId('concept-variant-pill-hair-a');
    await screen.findByTestId('concept-variant-pill-hair-c');
    const variantADot = screen.getByTestId('concept-variant-pill-dot-hair-a');
    const variantCDot = screen.getByTestId('concept-variant-pill-dot-hair-c');
    expect(parentDot?.className).toContain('bg-rose-500');
    expect(variantADot?.className).toContain('bg-slate-300');
    expect(variantCDot?.className).toContain('bg-rose-500');
  });

  it('renders review-needed source-item variants independently of untagged sibling rollups', async () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 44,
          key: 'hair',
          name: 'hair',
          tag: 'review' as const,
          variants: [
            { conceptKey: 'hair-a', conceptEn: 'hair (A)', variantLabel: 'A', tag: 'review' as const },
            { conceptKey: 'hair-c', conceptEn: 'hair (C)', variantLabel: 'C', tag: 'untagged' as const },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={44}
        activeConceptKey="hair-a"
        onConceptSelect={vi.fn()}
      />,
    );

    await screen.findByTestId('concept-variant-pill-hair-a');
    await screen.findByTestId('concept-variant-pill-hair-c');
    expect(screen.getByTestId('concept-variant-pill-dot-hair-a').className).toContain('bg-amber-400');
    expect(screen.getByTestId('concept-variant-pill-dot-hair-c').className).toContain('bg-slate-300');
  });
  it('renders review-needed source-item variants independently of confirmed sibling rollups', async () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 43,
          key: 'hair',
          name: 'hair',
          tag: 'confirmed' as const,
          variants: [
            { conceptKey: 'hair-a', conceptEn: 'hair (A)', variantLabel: 'A', tag: 'confirmed' as const },
            { conceptKey: 'hair-c', conceptEn: 'hair (C)', variantLabel: 'C', tag: 'review' as const },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={43}
        activeConceptKey="hair-a"
        onConceptSelect={vi.fn()}
      />,
    );

    await screen.findByTestId('concept-variant-pill-hair-a');
    await screen.findByTestId('concept-variant-pill-hair-c');
    const variantADot = screen.getByTestId('concept-variant-pill-dot-hair-a');
    const variantCDot = screen.getByTestId('concept-variant-pill-dot-hair-c');
    expect(variantADot?.className).toContain('bg-emerald-500');
    expect(variantCDot?.className).toContain('bg-amber-400');
  });

  it('renders the provided concept list with the active concept highlighted', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
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
    expect(screen.getByTestId('concept-row-2').textContent ?? '').toContain('2.1');
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
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
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
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
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
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
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
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
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
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
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

    expect(screen.getByTestId('concept-row-42').textContent ?? '').toContain('KLQ 1.2');
  });

  it('shows bare source item as the concept badge without a prefix when source survey is absent', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
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

    const text = screen.getByTestId('concept-row-42').textContent ?? '';
    expect(text).toContain('1.2');
    expect(text).not.toContain('#1.2');
  });

  it('falls back to a #id badge when no source item is present', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled
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

    expect(screen.getByTestId('concept-row-42').textContent ?? '').toContain('#42');
  });

  it('labels the source-aware sort tab as Source', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
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
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
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

    expect(screen.getByTestId('concept-row-42').textContent ?? '').toContain('KLQ 1.2');
    expect(screen.getByTestId('concept-row-43').textContent ?? '').toContain('#43');
    expect(screen.getByTestId('concept-sort-parent-source').getAttribute('aria-disabled')).toBeNull();
  });

  it('opens a context menu on right-click with merge and unmerge actions', () => {
    const onMergeRequest = vi.fn();
    const onUnmerge = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{ id: 1, name: 'head', tag: 'untagged' as const, mergedKeys: ['527', '247'], key: '527' }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        onMergeRequest={onMergeRequest}
        onUnmergeConcept={onUnmerge}
      />,
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: /head/i }));

    expect(screen.getByRole('menu')).toBeTruthy();
    fireEvent.click(screen.getByRole('menuitem', { name: /merge with/i }));
    expect(onMergeRequest).toHaveBeenCalledWith(expect.objectContaining({ id: 1, name: 'head' }));

    fireEvent.contextMenu(screen.getByRole('button', { name: /head/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /unmerge/i }));
    expect(onUnmerge).toHaveBeenCalledWith(expect.objectContaining({ id: 1, name: 'head' }));
  });

  it('keeps inline SurveyBadge text for single-survey and multi-survey rows', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[
          {
            id: 7,
            key: 'rain',
            name: 'rain',
            tag: 'untagged' as const,
            sourceItem: 'KLQ_1.10',
            sourceSurvey: 'klq',
            surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' },
          },
          {
            id: 8,
            key: 'snow',
            name: 'snow',
            tag: 'untagged' as const,
            sourceItem: 'KLQ_1.11',
            sourceSurvey: 'klq',
          },
        ]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={7}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail01"
        surveySettings={{
          klq: { display_label: 'Kurdish List', display_color: 'slate' },
          jbil: { display_label: 'Jbil Modal', display_color: 'slate' },
        }}
        speakerSurveyChoices={{ Fail01: { rain: 'jbil' } }}
        onSurveyChoiceChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('concept-row-7').textContent ?? '').toContain('Jbil Modal JBIL_100');
    expect(screen.getByTestId('concept-row-8').textContent ?? '').toContain('Kurdish List KLQ_1.11');
  });

  it('does not render the multi-survey switch chip row under sidebar rows', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 7,
          key: 'rain',
          name: 'rain',
          tag: 'untagged' as const,
          sourceItem: 'KLQ_1.10',
          sourceSurvey: 'klq',
          surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' },
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={7}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail01"
        surveySettings={{
          klq: { display_label: 'Kurdish List', display_color: 'slate' },
          jbil: { display_label: 'Jbil Modal', display_color: 'slate' },
        }}
        speakerSurveyChoices={{ Fail01: { rain: 'jbil' } }}
        onSurveyChoiceChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('concept-row-7').textContent ?? '').toContain('Jbil Modal JBIL_100');
    expect(screen.queryByRole('button', { name: /Switch rain to Kurdish List KLQ_1.10/i })).toBeNull();
  });

  it('lets users click the visible survey badge to flip to the next overlapping survey', () => {
    const onSurveyChoiceChange = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 7,
          key: 'rain',
          name: 'rain',
          tag: 'untagged' as const,
          sourceItem: 'KLQ_1.10',
          sourceSurvey: 'klq',
          surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' },
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={7}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail01"
        surveySettings={{
          klq: { display_label: 'Kurdish List', display_color: 'slate' },
          jbil: { display_label: 'Jbil Modal', display_color: 'slate' },
        }}
        speakerSurveyChoices={{ Fail01: { rain: 'jbil' } }}
        onSurveyChoiceChange={onSurveyChoiceChange}
      />,
    );

    const badge = screen.getByRole('button', { name: /Switch survey for rain from Jbil Modal JBIL_100 to Kurdish List KLQ_1.10/i });
    expect(badge.textContent ?? '').toContain('Jbil Modal JBIL_100');

    fireEvent.click(badge);

    expect(onSurveyChoiceChange).toHaveBeenCalledWith('Fail01', 'rain', 'klq');
  });

  it('shows a merge-count badge with absorbed names in the tooltip', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="az"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 1,
          name: 'head',
          tag: 'untagged' as const,
          mergedKeys: ['527', '247', '248'],
          mergeAbsorbedNames: ['head (A)', 'head (B)'],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('+2').getAttribute('title')).toContain('head (A)');
  });

  it('scopes rows to the active speaker elicited keys and matches merged or variant keys', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[
          { id: 1, key: '1', name: 'water', tag: 'untagged' as const },
          { id: 2, key: '2', name: 'fire', tag: 'confirmed' as const },
          { id: 3, key: 'display-3', name: 'brother of husband', tag: 'untagged' as const, mergedKeys: ['3a', '3b'] },
          { id: 4, key: 'display-4', name: 'variant row', tag: 'untagged' as const, variants: [{ conceptKey: '4b', conceptEn: 'variant row B', variantLabel: 'B' }] },
        ]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail02"
        scopedToSpeaker
        onScopedToSpeakerChange={vi.fn()}
        elicitedConceptKeys={new Set(['1', '3b', '4b'])}
      />,
    );

    const breadcrumb = screen.getByTestId('concept-scope-breadcrumb');
    expect(breadcrumb.textContent).toContain('3 in Fail02');
    expect(screen.getByRole('button', { name: /show all/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /fire/i })).toBeNull();
    expect(screen.getByRole('button', { name: /brother of husband/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /variant row/i })).toBeTruthy();
  });

  it('folds the unscoped active speaker toggle into the count breadcrumb', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[
          { id: 1, key: '1', name: 'water', tag: 'untagged' as const },
          { id: 2, key: '2', name: 'fire', tag: 'confirmed' as const },
        ]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail02"
        scopedToSpeaker={false}
        onScopedToSpeakerChange={vi.fn()}
        elicitedConceptKeys={new Set(['1'])}
      />,
    );

    const breadcrumb = screen.getByTestId('concept-scope-breadcrumb');
    expect(breadcrumb.textContent).toContain('2 concepts');
    expect(screen.getByRole('button', { name: /scope to speaker/i })).toBeTruthy();
  });

  it('does not surface hidden source-item variants in a scoped tag-filtered sidebar row', () => {
    const onSelect = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="source"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[{
          id: 1,
          key: '1.1',
          name: 'hair',
          tag: 'confirmed' as const,
          sourceItem: '1.1',
          sourceSurvey: 'KLQ',
          variants: [
            { conceptKey: '1', conceptEn: 'hair', variantLabel: '1' },
            { conceptKey: '599', conceptEn: 'hair (collective)', variantLabel: '599' },
          ],
        }]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set(['custom-sk-concept-list'])}
        onTagSelectionChange={vi.fn()}
        tags={[{ id: 'custom-sk-concept-list', name: 'Thesis', color: '#2563eb' }]}
        activeConceptId={1}
        activeConceptKey="1"
        onConceptSelect={onSelect}
        activeSpeaker="Saha01"
        scopedToSpeaker
        onScopedToSpeakerChange={vi.fn()}
        elicitedConceptKeys={new Set(['1'])}
        isConceptVariantVisibleInSidebar={(_concept, variant) => variant.conceptKey === '1'}
      />,
    );

    expect(screen.queryByTestId('concept-variant-toggle-1')).toBeNull();
    expect(screen.queryByText('hair (collective)')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /hair/i }));
    expect(onSelect).toHaveBeenCalledWith(1, '1');
  });

  it('shows all master rows with no-data suffixes when unscoped', () => {
    const onScopedToSpeakerChange = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={[
          { id: 1, key: '1', name: 'water', tag: 'untagged' as const },
          { id: 2, key: '2', name: 'fire', tag: 'confirmed' as const },
        ]}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail02"
        scopedToSpeaker={false}
        onScopedToSpeakerChange={onScopedToSpeakerChange}
        elicitedConceptKeys={new Set(['1'])}
      />,
    );

    const breadcrumb = screen.getByTestId('concept-scope-breadcrumb');
    expect(breadcrumb.textContent).toContain('2 concepts');
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    const fire = screen.getByRole('button', { name: /fire/i });
    expect(fire.className).toContain('text-slate-400');
    expect(fire.textContent ?? '').toContain('no data');
    fireEvent.click(screen.getByRole('button', { name: /scope to speaker/i }));
    expect(onScopedToSpeakerChange).toHaveBeenCalledWith(true);
  });

  it('falls back to the master list with an annotation-file note for an empty scoped set', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail02"
        scopedToSpeaker
        onScopedToSpeakerChange={vi.fn()}
        elicitedConceptKeys={new Set()}
      />,
    );

    expect(screen.getByText('No annotation file for Fail02 — showing master list')).toBeTruthy();
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /fire/i })).toBeTruthy();
  });

  it('renders concept count breadcrumb when scoped speaker has no annotation file', () => {
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortParent="concept"
        conceptSub="1n"
        sourceSub="time"
        onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
        sourceDisabled={false}
        filteredConcepts={baseConcepts}
        statusFilter="all"
        onStatusFilterChange={vi.fn()}
        selectedTagIds={new Set()}
        onTagSelectionChange={vi.fn()}
        tags={[]}
        activeConceptId={1}
        onConceptSelect={vi.fn()}
        activeSpeaker="Fail02"
        scopedToSpeaker
        onScopedToSpeakerChange={vi.fn()}
        elicitedConceptKeys={new Set()}
      />,
    );

    const breadcrumb = screen.getByTestId('concept-scope-breadcrumb');
    expect(breadcrumb.textContent).toContain('2 concepts');
    expect(breadcrumb.textContent).not.toContain('in Fail02');
    expect(screen.getByText('No annotation file for Fail02 — showing master list')).toBeTruthy();
    expect(screen.getByRole('button', { name: /show all/i })).toBeTruthy();
  });

  describe('right-click → + Add elicitation', () => {
    const concepts = [
      { id: 1, key: '1', name: 'leaf', tag: 'untagged' as const, sourceItem: '102' },
      { id: 2, key: '2', name: 'rain (A)', tag: 'untagged' as const, sourceItem: '125' },
      {
        id: 3,
        key: '154',
        name: 'new',
        tag: 'untagged' as const,
        sourceItem: '154',
        variants: [
          { conceptKey: '365', conceptEn: 'new (A)', variantLabel: 'A' },
          { conceptKey: '618', conceptEn: 'new (B)', variantLabel: 'B' },
        ],
      },
      { id: 4, key: '4', name: 'branch', tag: 'untagged' as const, sourceItem: '101' },
    ];

    function renderWith(onAddElicitation: (concept: unknown) => void, onDeleteConcept: (concept: unknown) => void = vi.fn()) {
      return render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={1}
          onConceptSelect={vi.fn()}
          onAddElicitation={onAddElicitation}
          onDeleteConcept={onDeleteConcept}
        />,
      );
    }

    function openMenuFor(name: RegExp): void {
      const buttons = screen.getAllByRole('button', { name });
      const button = buttons.find((candidate) => candidate.getAttribute('data-testid')?.startsWith('concept-parent-button')) ?? buttons[0];
      fireEvent.contextMenu(button);
    }

    it('fires onAddElicitation for a singleton concept', () => {
      const onAdd = vi.fn();
      renderWith(onAdd);
      openMenuFor(/^leaf/);
      const item = screen.getByRole('menuitem', { name: /\+ Add elicitation/ });
      expect(item.getAttribute('aria-disabled')).toBe('false');
      fireEvent.click(item);
      expect(onAdd).toHaveBeenCalledTimes(1);
      expect(onAdd.mock.calls[0][0].id).toBe(1);
    });

    it('keeps add elicitation enabled for grouped A/B concepts', () => {
      const onAdd = vi.fn();
      renderWith(onAdd);
      openMenuFor(/^new/);
      const item = screen.getByRole('menuitem', { name: /\+ Add elicitation/ });
      expect(item.getAttribute('aria-disabled')).toBe('false');
      expect(item.getAttribute('title')).toBe('Add another elicitation interval for this concept');
      fireEvent.click(item);
      expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ key: '154', name: 'new' }));
    });

    it('renders selectable variant child rows under an expanded grouped parent', () => {
      const onSelect = vi.fn();
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={3}
          activeConceptKey="618"
          onConceptSelect={onSelect}
        />,
      );

      expect(screen.getByTestId('concept-variant-pill-365').textContent ?? '').toContain('A');
      const rowB = screen.getByTestId('concept-variant-pill-618');
      expect(rowB.textContent ?? '').toContain('B');
      expect(rowB.className).toContain('bg-indigo-50');
      fireEvent.click(rowB);
      expect(onSelect).toHaveBeenCalledWith(3, '618');
    });

    it('confines active highlight to the active variant button, not the wrapper or siblings', () => {
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={3}
          activeConceptKey="365"
          onConceptSelect={vi.fn()}
        />,
      );

      const wrapper = screen.getByTestId('concept-row-3');
      expect(wrapper.className).not.toContain('bg-indigo-50');

      const rowA = screen.getByTestId('concept-variant-pill-365');
      expect(rowA.className).toContain('bg-indigo-50');

      const rowB = screen.getByTestId('concept-variant-pill-618');
      expect(rowB.className).not.toContain('bg-indigo-50');
    });

    it('does not light up the parent button when the first variant is selected', () => {
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={3}
          activeConceptKey="365"
          onConceptSelect={vi.fn()}
        />,
      );

      const parentButton = screen.getByTestId('concept-parent-button-3');
      expect(parentButton.className).not.toContain('bg-indigo-50');

      const rowA = screen.getByTestId('concept-variant-pill-365');
      expect(rowA.className).toContain('bg-indigo-50');

      const rowB = screen.getByTestId('concept-variant-pill-618');
      expect(rowB.className).not.toContain('bg-indigo-50');
    });

    it('auto-expands a grouped parent when activeConceptKey matches one of its variants', () => {
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={3}
          activeConceptKey="618"
          onConceptSelect={vi.fn()}
        />,
      );

      expect(screen.queryByTestId('concept-variant-toggle-3')).toBeNull();
      expect(screen.getByTestId('concept-variant-pill-618').textContent ?? '').toContain('B');
    });

    it('does not auto-expand when activeConceptKey is null', () => {
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={3}
          activeConceptKey={null}
          onConceptSelect={vi.fn()}
        />,
      );

      expect(screen.queryByTestId('concept-variant-toggle-3')).toBeNull();
      expect(screen.getByTestId('concept-variant-pill-618').textContent ?? '').toContain('B');
    });

    it('does not auto-expand when the active concept has zero or one variant', () => {
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortParent="concept"
        conceptSub="az"
        sourceSub="time"
          onSortParentChange={vi.fn()}
        onConceptSubChange={vi.fn()}
        onSourceSubChange={vi.fn()}
          sourceDisabled={false}
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={1}
          activeConceptKey="1"
          onConceptSelect={vi.fn()}
        />,
      );

      expect(screen.queryByTestId('concept-variant-toggle-1')).toBeNull();
      expect(screen.queryByTestId('concept-variant-toggle-4')).toBeNull();
    });

    it("right-click on a B child fires onAddElicitation with B's conceptKey", () => {
      const onAdd = vi.fn();
      renderWith(onAdd);
            fireEvent.contextMenu(screen.getByTestId('concept-variant-pill-618'));
      fireEvent.click(screen.getByRole('menuitem', { name: /\+ Add elicitation/ }));

      expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ key: '618', name: 'new (B)' }));
    });

    it("renders Delete variant on a child variant row's context menu", () => {
      renderWith(vi.fn());
            fireEvent.contextMenu(screen.getByTestId('concept-variant-pill-618'));

      expect(screen.getByRole('menuitem', { name: /Delete variant/i })).toBeTruthy();
    });

    it("does not render Delete variant on a grouped parent row's context menu", () => {
      renderWith(vi.fn());
      openMenuFor(/^new/);

      expect(screen.queryByRole('menuitem', { name: /Delete variant/i })).toBeNull();
    });

    it("calls onDeleteConcept with the child variant's conceptKey", () => {
      const onDelete = vi.fn();
      renderWith(vi.fn(), onDelete);
            fireEvent.contextMenu(screen.getByTestId('concept-variant-pill-618'));
      fireEvent.click(screen.getByRole('menuitem', { name: /Delete variant/i }));

      expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ key: '618', name: 'new (B)' }));
    });

    it('does not disable a stem-named concept when no variants are present', () => {
      const onAdd = vi.fn();
      renderWith(onAdd);
      openMenuFor(/^branch/);
      const item = screen.getByRole('menuitem', { name: /\+ Add elicitation/ });
      expect(item.getAttribute('aria-disabled')).toBe('false');
      fireEvent.click(item);
      expect(onAdd).toHaveBeenCalledTimes(1);
      expect(onAdd.mock.calls[0][0].id).toBe(4);
    });
  });

});
