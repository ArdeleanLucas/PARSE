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
      onSelectAllSpeakers={vi.fn()}
      onClearSpeakers={vi.fn()}
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
      workspaceConcepts={[]}
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

  it('keeps the phonetic section limited to real annotated tools', () => {
    renderRightPanel({
      currentMode: 'annotate',
      annotateSpeakerTools: <button type="button">Speaker-scoped tool</button>,
      annotateAuxTools: <button type="button">Auxiliary tool</button>,
    });

    const section = screen.getByRole('button', { name: /Phonetic tools/i }).closest('section');
    expect(section).not.toBeNull();
    expect(within(section as HTMLElement).getByRole('button', { name: 'Speaker-scoped tool' })).toBeTruthy();
    expect(within(section as HTMLElement).getByRole('button', { name: 'Auxiliary tool' })).toBeTruthy();
    expect(within(section as HTMLElement).getAllByRole('button')).toHaveLength(3);
  });

  it('renders Survey Values between Speakers and Timestamp tools with the active survey summary', () => {
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
      onSurveyOverlapUpdate: vi.fn(),
    });

    const surveyHeader = screen.getByRole('button', { name: /Survey Values/i });
    const timestampHeader = screen.getByRole('button', { name: /Timestamp tools/i });
    expect(surveyHeader.compareDocumentPosition(timestampHeader) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const summary = screen.getByTestId('survey-current-summary');
    expect(summary.textContent ?? '').toContain('Active survey');
    expect(summary.textContent ?? '').toContain('Jbil Modal');
    expect(summary.textContent ?? '').toContain('Source item');
    expect(summary.textContent ?? '').toContain('JBIL_100');
  });

  it('supports Survey Values label edit save/cancel and keeps color coding toggle enabled for a single survey', () => {
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
      workspaceConcepts: [{
        id: 7,
        key: 'rain',
        name: 'rain',
        tag: 'untagged',
        sourceItem: 'KLQ_1.10',
        sourceSurvey: 'klq',
        surveys: { klq: 'KLQ_1.10' },
      }],
      surveySettings: { klq: { display_label: 'Kurdish List', display_color: 'slate' } },
      onSurveyOverlapUpdate,
    });

    const colorToggle = screen.getByTestId('survey-color-coding-toggle') as HTMLButtonElement;
    expect(colorToggle.disabled).toBe(false);
    expect(colorToggle.title).toBe('Toggle survey color coding workspace-wide.');
    expect(colorToggle.getAttribute('data-toggle-state')).toBe('off');
    expect(colorToggle.getAttribute('data-toggle-style')).toBe('standalone');
    expect(document.querySelector('[data-toggle-state="off"][data-toggle-style="standalone"]')).toBe(colorToggle);

    fireEvent.click(screen.getByRole('button', { name: /Edit survey label Kurdish List/i }));
    const input = screen.getByLabelText('Survey label for klq') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'KLQ Field List' } });
    fireEvent.click(screen.getByRole('button', { name: /Save survey label klq/i }));

    expect(onSurveyOverlapUpdate).toHaveBeenCalledWith(expect.objectContaining({
      surveys: { klq: { display_label: 'KLQ Field List', display_color: 'slate' } },
    }));
  });

  it('updates color-coding toggle state when the controlled setting changes', () => {
    const activeConcept = {
      id: 7,
      key: 'rain',
      name: 'rain',
      tag: 'untagged',
      sourceItem: 'KLQ_1.10',
      sourceSurvey: 'klq',
      surveys: { klq: 'KLQ_1.10' },
    } as const;
    const onSurveyOverlapUpdate = vi.fn();
    const { rerender } = renderRightPanel({
      currentMode: 'annotate',
      selectedSpeakers: ['Fail01'],
      activeActionSpeaker: 'Fail01',
      activeConcept,
      workspaceConcepts: [activeConcept],
      surveyColorCodingEnabled: false,
      surveySettings: { klq: { display_label: 'Kurdish List', display_color: 'slate' } },
      onSurveyOverlapUpdate,
    });

    const toggle = screen.getByTestId('survey-color-coding-toggle');
    expect(toggle.getAttribute('data-toggle-state')).toBe('off');
    fireEvent.click(toggle);
    expect(onSurveyOverlapUpdate).toHaveBeenCalledWith({ color_coding_enabled: true });

    rerender(
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
        onSelectAllSpeakers={vi.fn()}
        onClearSpeakers={vi.fn()}
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
        workspaceConcepts={[activeConcept]}
        offsetPhase="idle"
        onDetectOffset={vi.fn()}
        onOpenManualOffset={vi.fn()}
        currentConceptId="c1"
        onSaveAnnotations={vi.fn()}
        activeConcept={activeConcept}
        surveyColorCodingEnabled
        surveySettings={{ klq: { display_label: 'Kurdish List', display_color: 'slate' } }}
        speakerSurveyChoices={{}}
        onSurveyOverlapUpdate={vi.fn()}
      />,
    );

    expect(screen.getByTestId('survey-color-coding-toggle').getAttribute('data-toggle-state')).toBe('on');
  });

  it('lists workspace-level surveys and updates color swatches/reset defaults', () => {
    const onSurveyOverlapUpdate = vi.fn();
    const activeConcept = {
      id: 7,
      key: 'rain',
      name: 'rain',
      tag: 'untagged',
      sourceItem: 'KLQ_1.10',
      sourceSurvey: 'klq',
      surveys: { klq: 'KLQ_1.10' },
    } as const;
    renderRightPanel({
      currentMode: 'annotate',
      selectedSpeakers: ['Fail01'],
      activeActionSpeaker: 'Fail01',
      activeConcept,
      workspaceConcepts: [
        activeConcept,
        { id: 8, key: 'fire', name: 'fire', tag: 'untagged', sourceItem: 'JBIL_2', sourceSurvey: 'jbil', surveys: { jbil: 'JBIL_2' } },
      ],
      surveyColorCodingEnabled: true,
      surveySettings: {
        klq: { display_label: 'Kurdish List', display_color: 'teal' },
        wals: { display_label: 'WALS', display_color: 'blue' },
      },
      onSurveyOverlapUpdate,
    });

    expect(screen.getByRole('button', { name: /Survey Values 3/i })).toBeTruthy();
    expect(screen.getAllByText('Kurdish List').length).toBeGreaterThan(0);
    expect(screen.getByText('jbil')).toBeTruthy();
    expect(screen.getByText('WALS')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Set Kurdish List color to rose' }));
    expect(onSurveyOverlapUpdate).toHaveBeenCalledWith({
      surveys: { klq: { display_label: 'Kurdish List', display_color: 'rose' } },
    });

    fireEvent.click(screen.getByRole('button', { name: /Reset survey display defaults/i }));
    expect(onSurveyOverlapUpdate).toHaveBeenCalledWith({
      reset_surveys: true,
      reset_speaker_choices: true,
      color_coding_enabled: false,
    });
    expect((screen.getByRole('button', { name: /Add survey placeholder/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('disables survey color swatches when workspace color coding is off', () => {
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
      workspaceConcepts: [{
        id: 7,
        key: 'rain',
        name: 'rain',
        tag: 'untagged',
        sourceItem: 'KLQ_1.10',
        sourceSurvey: 'klq',
        surveys: { klq: 'KLQ_1.10' },
      }],
      surveyColorCodingEnabled: false,
      surveySettings: { klq: { display_label: 'Kurdish List', display_color: 'slate' } },
    });

    expect(screen.getByText('Turn on color-coding to apply.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Set Kurdish List color to amber' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('collapses drawer sections when their headers are clicked', () => {
    renderRightPanel({ currentMode: 'annotate' });

    fireEvent.click(screen.getByRole('button', { name: /^Speakers SINGLE/i }));

    expect(screen.queryByText(/Concept list scoped to/i)).toBeNull();
    expect(screen.getByRole('button', { name: /Timestamp tools/i })).toBeTruthy();
  });

  it('renders speaker bulk actions disabled in annotate mode', () => {
    const onSelectAllSpeakers = vi.fn();
    const onClearSpeakers = vi.fn();

    renderRightPanel({
      currentMode: 'annotate',
      speakers: ['Fail01', 'Fail02', 'Kalh01'],
      selectedSpeakers: ['Fail01'],
      onSelectAllSpeakers,
      onClearSpeakers,
    });

    const selectAll = screen.getByTestId('speakers-select-all') as HTMLButtonElement;
    const clear = screen.getByTestId('speakers-clear') as HTMLButtonElement;

    expect(selectAll.disabled).toBe(true);
    expect(clear.disabled).toBe(true);
    expect(selectAll.getAttribute('aria-disabled')).toBe('true');
    expect(clear.getAttribute('aria-disabled')).toBe('true');

    fireEvent.click(selectAll);
    fireEvent.click(clear);

    expect(onSelectAllSpeakers).not.toHaveBeenCalled();
    expect(onClearSpeakers).not.toHaveBeenCalled();
  });

  it('renders speaker bulk actions enabled in compare mode and fires handlers', () => {
    const onSelectAllSpeakers = vi.fn();
    const onClearSpeakers = vi.fn();

    renderRightPanel({
      currentMode: 'compare',
      speakers: ['Fail01', 'Fail02', 'Kalh01'],
      selectedSpeakers: ['Fail01'],
      onSelectAllSpeakers,
      onClearSpeakers,
    });

    const selectAll = screen.getByTestId('speakers-select-all') as HTMLButtonElement;
    const clear = screen.getByTestId('speakers-clear') as HTMLButtonElement;

    expect(selectAll.disabled).toBe(false);
    expect(clear.disabled).toBe(false);
    expect(selectAll.getAttribute('aria-disabled')).toBeNull();
    expect(clear.getAttribute('aria-disabled')).toBeNull();

    fireEvent.click(selectAll);
    fireEvent.click(clear);

    expect(onSelectAllSpeakers).toHaveBeenCalledOnce();
    expect(onClearSpeakers).toHaveBeenCalledOnce();
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
        onSelectAllSpeakers={vi.fn()}
        onClearSpeakers={vi.fn()}
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
        workspaceConcepts={[]}
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
