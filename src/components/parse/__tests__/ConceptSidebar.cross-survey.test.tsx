// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { ConceptSidebar } from '../ConceptSidebar';
import { setConceptSurveyLink } from '../../../api/client';

vi.mock('../../../api/client', () => ({
  setConceptSurveyLink: vi.fn(),
  deleteConceptSurveyLink: vi.fn(),
}));

const baseProps = {
  query: '',
  onQueryChange: vi.fn(),
  sortMode: 'survey' as const,
  onSortModeChange: vi.fn(),
  hasSourceItems: true,
  statusFilter: 'all' as const,
  onStatusFilterChange: vi.fn(),
  selectedTagIds: new Set<string>(),
  onTagSelectionChange: vi.fn(),
  tags: [],
  activeConceptId: 527,
  onConceptSelect: vi.fn(),
  activeSpeaker: 'speakerKey',
  surveySettings: {
    klq: { display_label: 'KLQ', display_color: 'slate' },
    jbil: { display_label: 'JBIL', display_color: 'slate' },
  },
};

const crossSurveyConcept = {
  id: 527,
  key: 'conceptKey',
  name: 'head',
  tag: 'untagged' as const,
  sourceItem: '1.1',
  sourceSurvey: 'klq',
  surveys: { klq: '1.1', jbil: '31' },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  vi.mocked(setConceptSurveyLink).mockResolvedValue({ ok: true, concept: { id: '527', label: 'head', surveys: { klq: '1.2', jbil: '31' } }, survey_overlap: { version: 1, color_coding_enabled: false, surveys: {}, concept_survey_links: {}, speaker_choices: {} } });
});

describe('ConceptSidebar cross-survey linking', () => {
  it('clicks any multi-survey badge through the per-speaker choice cycle', () => {
    const onSurveyChoiceChange = vi.fn();
    const { rerender } = render(
      <ConceptSidebar
        {...baseProps}
        filteredConcepts={[crossSurveyConcept]}
        speakerSurveyChoices={{ speakerKey: { conceptKey: 'klq' } }}
        onSurveyChoiceChange={onSurveyChoiceChange}
      />,
    );

    const klqBadge = screen.getByRole('button', { name: /Switch survey for head from KLQ 1\.1 to JBIL 31/i });
    expect(klqBadge.textContent).toBe('KLQ 1.1');
    expect(klqBadge.className).toContain('hover:underline');

    fireEvent.click(klqBadge);
    expect(onSurveyChoiceChange).toHaveBeenCalledWith('speakerKey', 'conceptKey', 'jbil');

    rerender(
      <ConceptSidebar
        {...baseProps}
        filteredConcepts={[crossSurveyConcept]}
        speakerSurveyChoices={{ speakerKey: { conceptKey: 'jbil' } }}
        onSurveyChoiceChange={onSurveyChoiceChange}
      />,
    );
    expect(screen.getByRole('button', { name: /Switch survey for head from JBIL 31 to KLQ 1\.1/i }).textContent).toBe('JBIL 31');
  });

  it('opens an inline Change survey ID editor from the row context menu', () => {
    render(
      <ConceptSidebar
        {...baseProps}
        filteredConcepts={[crossSurveyConcept]}
        speakerSurveyChoices={{ speakerKey: { conceptKey: 'klq' } }}
        onSurveyChoiceChange={vi.fn()}
      />,
    );

    fireEvent.contextMenu(within(screen.getByTestId('concept-row-527')).getByRole('button', { name: /^head KLQ 1\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));

    expect((screen.getByLabelText('survey_id') as HTMLSelectElement).value).toBe('klq');
    expect((screen.getByLabelText('source_item') as HTMLInputElement).value).toBe('1.1');
  });

  it('submits manual survey-link edits through the typed API helper', async () => {
    const onSurveyLinksChanged = vi.fn();
    render(
      <ConceptSidebar
        {...baseProps}
        filteredConcepts={[crossSurveyConcept]}
        speakerSurveyChoices={{ speakerKey: { conceptKey: 'klq' } }}
        onSurveyChoiceChange={vi.fn()}
        onSurveyLinksChanged={onSurveyLinksChanged}
      />,
    );

    fireEvent.contextMenu(within(screen.getByTestId('concept-row-527')).getByRole('button', { name: /^head KLQ 1\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));
    fireEvent.change(screen.getByLabelText('source_item'), { target: { value: '1.2' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(setConceptSurveyLink).toHaveBeenCalledWith('conceptKey', { survey_id: 'klq', source_item: '1.2' }));
    await waitFor(() => expect(onSurveyLinksChanged).toHaveBeenCalled());
  });
});
