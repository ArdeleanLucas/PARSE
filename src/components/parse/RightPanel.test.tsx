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
      tagFilter="all"
      onTagFilterChange={vi.fn()}
      onOpenLoadDecisions={vi.fn()}
      onSaveDecisions={vi.fn()}
      onExportLingPy={vi.fn()}
      exporting={false}
      onOpenCommentsImport={vi.fn()}
      activeActionSpeaker="Fail01"
      offsetPhase="idle"
      onDetectOffset={vi.fn()}
      onOpenManualOffset={vi.fn()}
      onSaveAnnotations={vi.fn()}
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
        tagFilter="all"
        onTagFilterChange={vi.fn()}
        onOpenLoadDecisions={vi.fn()}
        onSaveDecisions={vi.fn()}
        onExportLingPy={vi.fn()}
        exporting={false}
        onOpenCommentsImport={vi.fn()}
        activeActionSpeaker="Fail01"
        offsetPhase="idle"
        onDetectOffset={vi.fn()}
        onOpenManualOffset={vi.fn()}
        onSaveAnnotations={vi.fn()}
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
