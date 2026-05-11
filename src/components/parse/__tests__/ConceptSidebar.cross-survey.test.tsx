// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { ConceptSidebar } from '../ConceptSidebar';
import { deleteConceptSurveyLink, setConceptSurveyLink } from '../../../api/client';

vi.mock('../../../api/client', () => ({
  setConceptSurveyLink: vi.fn(),
  deleteConceptSurveyLink: vi.fn(),
}));

const baseProps = {
  query: '',
  onQueryChange: vi.fn(),
  sortParent: 'source' as const,
  conceptSub: '1n' as const,
  sourceSub: 'time' as const,
  onSortParentChange: vi.fn(),
  onConceptSubChange: vi.fn(),
  onSourceSubChange: vi.fn(),
  sourceDisabled: false,
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
    sil: { display_label: 'SIL', display_color: 'slate' },
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

const groupedBigConcept = {
  id: 53,
  key: '4.1',
  name: 'big',
  tag: 'untagged' as const,
  sourceItem: '4.1',
  sourceSurvey: 'klq',
  surveys: { klq: '4.1', jbil: '169' },
  variants: [
    { conceptKey: '53', conceptEn: 'big (A)', variantLabel: 'A' },
    { conceptKey: '619', conceptEn: 'big (B)', variantLabel: 'B' },
  ],
};

function renderSidebar(overrides = {}) {
  return render(
    <ConceptSidebar
      {...baseProps}
      filteredConcepts={[groupedBigConcept]}
      activeConceptId={53}
      activeSpeaker="Saha01"
      conceptSurveyLinks={{
        '53': { klq: '4.1' },
        '619': { klq: '4.1' },
      }}
      speakerConceptSurveyLinks={{}}
      onSurveyChoiceChange={vi.fn()}
      {...overrides}
    />,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  vi.mocked(setConceptSurveyLink).mockResolvedValue({ ok: true, concept: { id: '527', label: 'head', surveys: { klq: '1.2', jbil: '31' }, speaker_surveys: { klq: '1.2' } }, survey_overlap: { version: 1, color_coding_enabled: false, surveys: {}, concept_survey_links: {}, speaker_choices: {}, speaker_concept_survey_links: {} } });
  vi.mocked(deleteConceptSurveyLink).mockResolvedValue({ ok: true, concept: { id: '527', label: 'head', surveys: { jbil: '31' } }, survey_overlap: { version: 1, color_coding_enabled: false, surveys: {}, concept_survey_links: {}, speaker_choices: {}, speaker_concept_survey_links: {} } });
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

  it('opens a bucket-aware Change survey ID editor from the row context menu', () => {
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

    expect(screen.getByText('Current buckets')).toBeTruthy();
    expect((screen.getByLabelText('survey_id') as HTMLSelectElement).value).toBe('klq');
    expect((screen.getByLabelText('source_item') as HTMLInputElement).value).toBe('1.1');
  });

  it('submits manual survey-link edits through the typed API helper with speaker scope', async () => {
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

    await waitFor(() => expect(setConceptSurveyLink).toHaveBeenCalledWith('conceptKey', { survey_id: 'klq', source_item: '1.2', speaker: 'speakerKey' }));
    await waitFor(() => expect(onSurveyLinksChanged).toHaveBeenCalled());
  });

  it('disables Save on a grouped parent when no active speaker is selected', () => {
    renderSidebar({ activeSpeaker: null });

    fireEvent.contextMenu(within(screen.getByTestId('concept-row-53')).getByRole('button', { name: /^big KLQ 4\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));

    const saveButton = screen.getByRole('button', { name: /^Save$/i }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
    expect(saveButton.title).toBe('Select a speaker before changing the survey ID for a grouped concept.');
  });

  it('enables Save on a grouped parent once an active speaker is selected', () => {
    const { rerender } = renderSidebar({ activeSpeaker: null });

    fireEvent.contextMenu(within(screen.getByTestId('concept-row-53')).getByRole('button', { name: /^big KLQ 4\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));
    rerender(
      <ConceptSidebar
        {...baseProps}
        filteredConcepts={[groupedBigConcept]}
        activeConceptId={53}
        activeSpeaker="Saha01"
        conceptSurveyLinks={{ '53': { klq: '4.1' }, '619': { klq: '4.1' } }}
        speakerConceptSurveyLinks={{}}
        onSurveyChoiceChange={vi.fn()}
      />,
    );

    const saveButton = screen.getByRole('button', { name: /^Save$/i }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    expect(saveButton.title).toBe('');
  });

  it('keeps Save enabled for a child variant when no active speaker is selected', () => {
    renderSidebar({ activeSpeaker: null });

    fireEvent.click(screen.getByTestId('concept-variant-toggle-53'));
    fireEvent.contextMenu(screen.getByTestId('concept-variant-row-53'));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));

    const saveButton = screen.getByRole('button', { name: /^Save$/i }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);
    expect(saveButton.title).toBe('');
  });

  it('saves a grouped parent bucket with comma-separated csv row ids instead of the synthetic key', async () => {
    const onSurveyLinksChanged = vi.fn();
    renderSidebar({ onSurveyLinksChanged });

    fireEvent.contextMenu(within(screen.getByTestId('concept-row-53')).getByRole('button', { name: /^big KLQ 4\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));
    expect(screen.getByText(/Will update variants: A \(id 53\), B \(id 619\)/i)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('source_item'), { target: { value: '4.2' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(setConceptSurveyLink).toHaveBeenCalledWith('53,619', { survey_id: 'klq', source_item: '4.2', speaker: 'Saha01' }));
    await waitFor(() => expect(onSurveyLinksChanged).toHaveBeenCalled());
  });

  it('saves a child variant bucket with only that row id', async () => {
    renderSidebar();
    fireEvent.click(screen.getByTestId('concept-variant-toggle-53'));
    fireEvent.contextMenu(screen.getByTestId('concept-variant-row-53'));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));
    fireEvent.change(screen.getByLabelText('source_item'), { target: { value: '4.3' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(setConceptSurveyLink).toHaveBeenCalledWith('53', { survey_id: 'klq', source_item: '4.3', speaker: 'Saha01' }));
  });

  it('adds a new link to every grouped parent variant id', async () => {
    renderSidebar();
    fireEvent.contextMenu(within(screen.getByTestId('concept-row-53')).getByRole('button', { name: /^big KLQ 4\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));
    fireEvent.click(screen.getByRole('button', { name: /Add new link/i }));
    fireEvent.change(screen.getByLabelText('survey_id'), { target: { value: 'jbil' } });
    fireEvent.change(screen.getByLabelText('source_item'), { target: { value: '169' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(setConceptSurveyLink).toHaveBeenCalledWith('53,619', { survey_id: 'jbil', source_item: '169', speaker: 'Saha01' }));
  });

  it('removes an existing bucket with bucket row ids and speaker scope', async () => {
    renderSidebar();
    fireEvent.contextMenu(within(screen.getByTestId('concept-row-53')).getByRole('button', { name: /^big KLQ 4\.1$/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Change survey ID/i }));
    fireEvent.click(screen.getByRole('button', { name: /Remove link/i }));

    await waitFor(() => expect(deleteConceptSurveyLink).toHaveBeenCalledWith('53,619', { survey_id: 'klq', source_item: '4.1', speaker: 'Saha01' }));
  });

  it('renders speaker-specific buckets after switching speakers', () => {
    const { rerender } = renderSidebar({
      speakerConceptSurveyLinks: { Saha01: { '53': { jbil: '169' }, '619': { jbil: '169' } } },
    });
    expect(screen.getByText('JBIL 169')).toBeTruthy();

    rerender(
      <ConceptSidebar
        {...baseProps}
        filteredConcepts={[groupedBigConcept]}
        activeConceptId={53}
        activeSpeaker="Fail01"
        conceptSurveyLinks={{ '53': { klq: '4.1' }, '619': { klq: '4.1' } }}
        speakerConceptSurveyLinks={{ Fail01: { '53': { klq: '4.9' }, '619': { klq: '4.9' } } }}
        onSurveyChoiceChange={vi.fn()}
      />,
    );
    expect(screen.getByText('KLQ 4.9')).toBeTruthy();
  });
});
