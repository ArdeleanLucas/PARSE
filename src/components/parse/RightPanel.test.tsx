// @vitest-environment jsdom
import type { ComponentProps } from 'react';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { RightPanel } from './RightPanel';

afterEach(() => {
  cleanup();
});

function renderRightPanel(overrides: Partial<ComponentProps<typeof RightPanel>> = {}) {
  return render(
    <RightPanel
      panelOpen
      onTogglePanel={vi.fn()}
      currentMode="annotate"
      selectedSpeakers={['Fail01']}
      speakers={['Fail01', 'Fail02']}
      conceptCount={2}
      speakerPicker="Fail02"
      onSpeakerSelect={vi.fn()}
      onAddSpeaker={vi.fn()}
      onToggleSpeaker={vi.fn()}
      computeMode="cognates"
      onComputeModeChange={vi.fn()}
      onComputeRun={vi.fn()}
      crossSpeakerJobStatus="idle"
      computeJobStatus="idle"
      computeJobProgress={0}
      computeJobEtaMs={null}
      computeJobError={null}
      clefConfigured={false}
      onOpenSourcesReport={vi.fn()}
      onOpenClefConfig={vi.fn()}
      onRefreshEnrichments={vi.fn()}
      onOpenLoadDecisions={vi.fn()}
      onSaveDecisions={vi.fn()}
      onExportLingPy={vi.fn()}
      exporting={false}
      onOpenCommentsImport={vi.fn()}
      activeActionSpeaker="Fail01"
      offsetPhase="idle"
      onDetectOffset={vi.fn()}
      onOpenManualOffset={vi.fn()}
      currentConceptId="c1"
      onSaveAnnotations={vi.fn()}
      surveyColorCodingEnabled={false}
      surveySettings={{}}
      speakerSurveyChoices={{}}
      onSurveyOverlapUpdate={vi.fn()}
      {...overrides}
    />,
  );
}

describe('RightPanel', () => {
  it('preserves speaker-selection behavior in annotate mode', () => {
    const onSpeakerSelect = vi.fn();
    const onToggleSpeaker = vi.fn();
    const onSaveAnnotations = vi.fn();

    renderRightPanel({
      currentMode: 'annotate',
      selectedSpeakers: ['Fail01'],
      onSpeakerSelect,
      onToggleSpeaker,
      onSaveAnnotations,
    });

    const speakerPicker = within(screen.getByTestId('right-panel')).getAllByRole('combobox')[0];
    fireEvent.change(speakerPicker, { target: { value: 'Fail02' } });
    fireEvent.click(screen.getByRole('button', { name: 'Fail02' }));
    fireEvent.click(screen.getByRole('button', { name: /save annotations/i }));

    expect(onSpeakerSelect).toHaveBeenCalledWith('Fail02');
    expect(onToggleSpeaker).toHaveBeenCalledWith('Fail02');
    expect(onSaveAnnotations).toHaveBeenCalledOnce();
    expect(screen.getByText(/Concept list scoped to/i)).toBeTruthy();
  });

  it('does not render concept filters in annotate mode while keeping Save annotations', () => {
    renderRightPanel({ currentMode: 'annotate' });

    const panel = screen.getByTestId('right-panel');
    expect(within(panel).queryByText(/Filter concepts/i)).toBeNull();
    expect(within(panel).queryByRole('button', { name: 'All concepts' })).toBeNull();
    expect(within(panel).queryByRole('button', { name: 'Untagged' })).toBeNull();
    expect(within(panel).queryByRole('button', { name: 'Review needed' })).toBeNull();
    expect(within(panel).queryByRole('button', { name: 'Confirmed' })).toBeNull();
    expect(within(panel).queryByRole('button', { name: 'Problematic' })).toBeNull();
    expect(within(panel).getByRole('button', { name: /save annotations/i })).toBeTruthy();
  });

  it('renders Survey Values between Speakers and Timestamp tools and persists per-speaker flips', () => {
    const onSurveyOverlapUpdate = vi.fn();
    renderRightPanel({
      currentMode: 'annotate',
      selectedSpeakers: ['Fail01'],
      activeActionSpeaker: 'Fail01',
      activeConcept: {
        id: 7,
        key: 'rain',
        name: 'rain',
        tag: 'untagged',
        sourceItem: 'KLQ_1.10',
        sourceSurvey: 'klq',
        surveys: { klq: 'KLQ_1.10', jbil: 'JBIL_100' },
      },
      surveySettings: {
        klq: { display_label: 'Kurdish List', display_color: 'slate' },
        jbil: { display_label: 'Jbil Modal', display_color: 'slate' },
      },
      speakerSurveyChoices: { Fail01: { rain: 'jbil' } },
      onSurveyOverlapUpdate,
    });

    const surveyHeader = screen.getByRole('button', { name: /Survey Values/i });
    const timestampHeader = screen.getByRole('button', { name: /Timestamp tools/i });
    expect(surveyHeader.compareDocumentPosition(timestampHeader) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/Current survey/i).textContent ?? '').toContain('Jbil Modal');

    fireEvent.click(screen.getByRole('button', { name: /Switch rain to Kurdish List KLQ_1.10/i }));

    expect(onSurveyOverlapUpdate).toHaveBeenCalledWith(expect.objectContaining({
      speaker_choices: { Fail01: { rain: 'klq' } },
    }));
  });

  it('supports Survey Values label edit save/cancel and disables color coding when no overlap exists', () => {
    const onSurveyOverlapUpdate = vi.fn();
    renderRightPanel({
      currentMode: 'annotate',
      selectedSpeakers: ['Fail01'],
      activeActionSpeaker: 'Fail01',
      activeConcept: {
        id: 7,
        key: 'rain',
        name: 'rain',
        tag: 'untagged',
        sourceItem: 'KLQ_1.10',
        sourceSurvey: 'klq',
        surveys: { klq: 'KLQ_1.10' },
      },
      surveySettings: { klq: { display_label: 'Kurdish List', display_color: 'slate' } },
      onSurveyOverlapUpdate,
    });

    const colorToggle = screen.getByTestId('survey-color-coding-toggle') as HTMLButtonElement;
    expect(colorToggle.disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /Edit survey label Kurdish List/i }));
    const input = screen.getByLabelText('Survey label for klq') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'KLQ Field List' } });
    fireEvent.click(screen.getByRole('button', { name: /Save survey label klq/i }));

    expect(onSurveyOverlapUpdate).toHaveBeenCalledWith(expect.objectContaining({
      surveys: { klq: { display_label: 'KLQ Field List', display_color: 'slate' } },
    }));
  });

  it('collapses drawer sections when their headers are clicked', () => {
    renderRightPanel({ currentMode: 'annotate' });

    fireEvent.click(screen.getByRole('button', { name: /Speakers/i }));

    expect(screen.queryByText(/Concept list scoped to/i)).toBeNull();
    expect(screen.getByRole('button', { name: /Timestamp tools/i })).toBeTruthy();
  });

  it('preserves speaker-selection behavior in compare mode', () => {
    const onSpeakerSelect = vi.fn();
    const onAddSpeaker = vi.fn();
    const onToggleSpeaker = vi.fn();
    const onExportLingPy = vi.fn();
    const onOpenCommentsImport = vi.fn();

    renderRightPanel({
      currentMode: 'compare',
      selectedSpeakers: ['Fail01'],
      onSpeakerSelect,
      onAddSpeaker,
      onToggleSpeaker,
      onExportLingPy,
      onOpenCommentsImport,
    });

    const speakerPicker = within(screen.getByTestId('right-panel')).getAllByRole('combobox')[0];
    fireEvent.change(speakerPicker, { target: { value: 'Fail02' } });
    fireEvent.click(screen.getByTestId('add-speaker-button'));
    fireEvent.click(screen.getByRole('button', { name: 'Fail01' }));
    fireEvent.click(screen.getByRole('button', { name: /export lingpy tsv/i }));
    fireEvent.click(screen.getByTestId('open-comments-import'));

    expect(onSpeakerSelect).toHaveBeenCalledWith('Fail02');
    expect(onAddSpeaker).toHaveBeenCalledOnce();
    expect(onToggleSpeaker).toHaveBeenCalledWith('Fail01');
    expect(onExportLingPy).toHaveBeenCalledOnce();
    expect(onOpenCommentsImport).toHaveBeenCalledOnce();
  });

  it('wires compare compute controls without rendering the rebuild-only explainer drift', () => {
    const onComputeModeChange = vi.fn();
    const onComputeRun = vi.fn();
    const onRefreshEnrichments = vi.fn();
    const onOpenClefConfig = vi.fn();
    const onOpenSourcesReport = vi.fn();

    renderRightPanel({
      currentMode: 'compare',
      selectedSpeakers: ['Fail01', 'Fail02'],
      computeMode: 'contact-lexemes',
      clefConfigured: false,
      onComputeModeChange,
      onComputeRun,
      onRefreshEnrichments,
      onOpenClefConfig,
      onOpenSourcesReport,
    });

    const panel = screen.getByTestId('right-panel');
    const computeModePicker = within(panel).getAllByRole('combobox')[1];
    fireEvent.change(computeModePicker, { target: { value: 'similarity' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    fireEvent.click(screen.getByRole('button', { name: 'Configure' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sources Report' }));

    expect(onComputeModeChange).toHaveBeenCalledWith('similarity');
    expect(onComputeRun).toHaveBeenCalledOnce();
    expect(onRefreshEnrichments).toHaveBeenCalledOnce();
    expect(onOpenClefConfig).toHaveBeenCalledOnce();
    expect(onOpenSourcesReport).toHaveBeenCalledOnce();
    expect(screen.getByText(/CLEF not configured/i)).toBeTruthy();
    expect(screen.queryByTestId('compare-compute-semantics')).toBeNull();
    expect(screen.queryByText('Filter by tag')).toBeNull();
  });

  it('uses separate disabled and status semantics for contact and non-contact compute modes', () => {
    const { rerender } = renderRightPanel({
      currentMode: 'compare',
      selectedSpeakers: ['Fail01'],
      computeMode: 'similarity',
      computeJobStatus: 'running',
      computeJobProgress: 0.42,
      computeJobEtaMs: 25_000,
    });

    let runButton = screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
    expect(screen.getByText(/Running… 42%/i)).toBeTruthy();
    expect(screen.getByText(/25s left/i)).toBeTruthy();
    expect(screen.queryByText(/CLEF configured/i)).toBeNull();

    rerender(
      <RightPanel
        panelOpen
        onTogglePanel={vi.fn()}
        currentMode="compare"
        selectedSpeakers={['Fail01']}
        speakers={['Fail01', 'Fail02']}
        conceptCount={2}
        speakerPicker="Fail02"
        onSpeakerSelect={vi.fn()}
        onAddSpeaker={vi.fn()}
        onToggleSpeaker={vi.fn()}
        computeMode="contact-lexemes"
        onComputeModeChange={vi.fn()}
        onComputeRun={vi.fn()}
        crossSpeakerJobStatus="running"
        computeJobStatus="error"
        computeJobProgress={0.42}
        computeJobEtaMs={25_000}
        computeJobError="Similarity failed"
        clefConfigured
        onOpenSourcesReport={vi.fn()}
        onOpenClefConfig={vi.fn()}
        onRefreshEnrichments={vi.fn()}
        onOpenLoadDecisions={vi.fn()}
        onSaveDecisions={vi.fn()}
        onExportLingPy={vi.fn()}
        exporting={false}
        onOpenCommentsImport={vi.fn()}
        activeActionSpeaker="Fail01"
        offsetPhase="idle"
        onDetectOffset={vi.fn()}
        onOpenManualOffset={vi.fn()}
        currentConceptId="c1"
        onSaveAnnotations={vi.fn()}
        surveyColorCodingEnabled={false}
        surveySettings={{}}
        speakerSurveyChoices={{}}
        onSurveyOverlapUpdate={vi.fn()}
      />,
    );

    runButton = screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
    expect(screen.getByText(/CLEF configured/i)).toBeTruthy();
    expect(screen.queryByText(/Running… 42%/i)).toBeNull();
    expect(screen.queryByText(/Similarity failed/i)).toBeNull();
  });

  it('still disables generic compare Run when no speakers are selected without adding an extra explainer block', () => {
    renderRightPanel({
      currentMode: 'compare',
      selectedSpeakers: [],
      speakerPicker: 'Fail01',
    });

    const runButton = screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
    expect(screen.queryByTestId('compare-compute-semantics')).toBeNull();
    expect(screen.queryByText(/Selected speakers only:/i)).toBeNull();
  });
});
