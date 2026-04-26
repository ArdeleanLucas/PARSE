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

  it('does not render the extra compare compute semantics explainer from the rebuild-only parity drift', () => {
    renderRightPanel({
      currentMode: 'compare',
      selectedSpeakers: ['Fail01', 'Fail02'],
      computeMode: 'similarity',
    });

    expect(screen.queryByTestId('compare-compute-semantics')).toBeNull();
    expect(screen.queryByText(/Selected speakers only:/i)).toBeNull();
    expect(screen.queryByText(/shared backend recompute path as Cognates/i)).toBeNull();
    expect(screen.queryByText(/Refresh reloads saved enrichments only/i)).toBeNull();
  });

  it('still disables generic compare Run when no speakers are selected without adding an extra explainer block', () => {
    renderRightPanel({
      currentMode: 'compare',
      selectedSpeakers: [],
      computeMode: 'cognates',
    });

    const runButton = screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
    expect(screen.queryByTestId('compare-compute-semantics')).toBeNull();
    expect(screen.queryByText(/Selected speakers only:/i)).toBeNull();
  });
});
