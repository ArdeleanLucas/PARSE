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

    expect(screen.getByTestId('concept-row-42').textContent ?? '').toContain('KLQ 1.2');
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

    const text = screen.getByTestId('concept-row-42').textContent ?? '';
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

    expect(screen.getByTestId('concept-row-42').textContent ?? '').toContain('#42');
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

    expect(screen.getByTestId('concept-row-42').textContent ?? '').toContain('KLQ 1.2');
    expect(screen.getByTestId('concept-row-43').textContent ?? '').toContain('#43');
    expect(screen.getByTestId('concept-sort-survey').hasAttribute('disabled')).toBe(false);
  });

  it('opens a context menu on right-click with merge and unmerge actions', () => {
    const onMergeRequest = vi.fn();
    const onUnmerge = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="az"
        onSortModeChange={vi.fn()}
        hasSourceItems
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

  it('renders Approach A survey pills and sends per-speaker choice flips', () => {
    const onSurveyChoiceChange = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="survey"
        onSortModeChange={vi.fn()}
        hasSourceItems
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

    expect(screen.getByTestId('concept-row-7').textContent ?? '').toContain('Jbil Modal JBIL_100');

    fireEvent.click(screen.getByRole('button', { name: /Switch rain to Kurdish List KLQ_1.10/i }));

    expect(onSurveyChoiceChange).toHaveBeenCalledWith('Fail01', 'rain', 'klq');
  });

  it('lets users click the visible survey badge to flip to the next overlapping survey', () => {
    const onSurveyChoiceChange = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="survey"
        onSortModeChange={vi.fn()}
        hasSourceItems
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
        sortMode="az"
        onSortModeChange={vi.fn()}
        hasSourceItems
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
        sortMode="1n"
        onSortModeChange={vi.fn()}
        hasSourceItems
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

    expect(screen.getByText('Scoped to Fail02')).toBeTruthy();
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /fire/i })).toBeNull();
    expect(screen.getByRole('button', { name: /brother of husband/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /variant row/i })).toBeTruthy();
    expect(screen.getByText('3 concepts')).toBeTruthy();
  });

  it('shows all master rows with no-data suffixes when unscoped', () => {
    const onScopedToSpeakerChange = vi.fn();
    render(
      <ConceptSidebar
        query=""
        onQueryChange={vi.fn()}
        sortMode="1n"
        onSortModeChange={vi.fn()}
        hasSourceItems
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

    expect(screen.getByText('Showing all 2 master')).toBeTruthy();
    expect(screen.getByRole('button', { name: /water/i })).toBeTruthy();
    const fire = screen.getByRole('button', { name: /fire/i });
    expect(fire.className).toContain('text-slate-400');
    expect(fire.textContent ?? '').toContain('no data');
    fireEvent.click(screen.getByRole('button', { name: /Scope to speaker/i }));
    expect(onScopedToSpeakerChange).toHaveBeenCalledWith(true);
  });

  it('falls back to the master list with an annotation-file note for an empty scoped set', () => {
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


  describe('right-click → Duplicate (split into next variant)', () => {
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

    function renderWith(onDuplicateConcept: (concept: unknown) => void) {
      return render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortMode="az"
          onSortModeChange={vi.fn()}
          hasSourceItems
          filteredConcepts={concepts}
          statusFilter="all"
          onStatusFilterChange={vi.fn()}
          selectedTagIds={new Set()}
          onTagSelectionChange={vi.fn()}
          tags={[]}
          activeConceptId={1}
          onConceptSelect={vi.fn()}
          onDuplicateConcept={onDuplicateConcept}
        />,
      );
    }

    function openMenuFor(name: RegExp): void {
      const button = screen.getByRole('button', { name });
      fireEvent.contextMenu(button);
    }

    it('fires onDuplicateConcept for a singleton concept', () => {
      const onDuplicate = vi.fn();
      renderWith(onDuplicate);
      openMenuFor(/^leaf/);
      const item = screen.getByRole('menuitem', { name: /Duplicate \(split into next variant\)/ });
      expect(item.getAttribute('aria-disabled')).toBe('false');
      fireEvent.click(item);
      expect(onDuplicate).toHaveBeenCalledTimes(1);
      expect(onDuplicate.mock.calls[0][0].id).toBe(1);
    });

    it('keeps duplicate enabled for grouped A/B concepts', () => {
      const onDuplicate = vi.fn();
      renderWith(onDuplicate);
      openMenuFor(/^new/);
      const item = screen.getByRole('menuitem', { name: /Duplicate \(split into next variant\)/ });
      expect(item.getAttribute('aria-disabled')).toBe('false');
      expect(item.getAttribute('title')).toBe('Add a new variant');
      fireEvent.click(item);
      expect(onDuplicate).toHaveBeenCalledWith(expect.objectContaining({ key: '154', name: 'new' }));
    });

    it('renders selectable variant child rows under an expanded grouped parent', () => {
      const onSelect = vi.fn();
      render(
        <ConceptSidebar
          query=""
          onQueryChange={vi.fn()}
          sortMode="az"
          onSortModeChange={vi.fn()}
          hasSourceItems
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

      fireEvent.click(screen.getByTestId('concept-variant-toggle-3'));

      expect(screen.getByTestId('concept-variant-row-365').textContent ?? '').toContain('new (A)');
      const rowB = screen.getByTestId('concept-variant-row-618');
      expect(rowB.textContent ?? '').toContain('new (B)');
      expect(rowB.className).toContain('bg-indigo-50');
      fireEvent.click(rowB);
      expect(onSelect).toHaveBeenCalledWith(3, '618');
    });

    it("right-click on a B child fires onDuplicateConcept with B's conceptKey", () => {
      const onDuplicate = vi.fn();
      renderWith(onDuplicate);
      fireEvent.click(screen.getByTestId('concept-variant-toggle-3'));
      fireEvent.contextMenu(screen.getByTestId('concept-variant-row-618'));
      fireEvent.click(screen.getByRole('menuitem', { name: /Duplicate \(split into next variant\)/ }));

      expect(onDuplicate).toHaveBeenCalledWith(expect.objectContaining({ key: '618', name: 'new (B)' }));
    });

    it('does not disable a stem-named concept when no variants are present', () => {
      const onDuplicate = vi.fn();
      renderWith(onDuplicate);
      openMenuFor(/^branch/);
      const item = screen.getByRole('menuitem', { name: /Duplicate \(split into next variant\)/ });
      expect(item.getAttribute('aria-disabled')).toBe('false');
      fireEvent.click(item);
      expect(onDuplicate).toHaveBeenCalledTimes(1);
      expect(onDuplicate.mock.calls[0][0].id).toBe(4);
    });
  });

});
