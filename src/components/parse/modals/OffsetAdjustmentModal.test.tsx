// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { OffsetDetectResult } from '../../../api/client';
import { OffsetAdjustmentModal } from './OffsetAdjustmentModal';

function makeDetectedResult(overrides: Partial<OffsetDetectResult> = {}): OffsetDetectResult {
  return {
    speaker: 'Fail01',
    offsetSec: 1.5,
    confidence: 0.88,
    nAnchors: 2,
    totalAnchors: 2,
    totalSegments: 12,
    method: 'manual_pair',
    ...overrides,
  };
}

describe('OffsetAdjustmentModal', () => {
  it('renders manual anchors with live consensus and forwards anchor-management callbacks', () => {
    const onClose = vi.fn();
    const onCaptureCurrentSelection = vi.fn();
    const onRemoveManualAnchor = vi.fn();
    const onSubmitManualOffset = vi.fn();

    render(
      <OffsetAdjustmentModal
        open
        offsetState={{ phase: 'manual' }}
        manualAnchors={[
          {
            conceptKey: '1',
            conceptName: 'water',
            csvTimeSec: 8,
            audioTimeSec: 9.5,
            capturedAt: 100,
          },
        ]}
        manualConsensus={{ median: 1.5, mad: 0, offsets: [1.5] }}
        manualBusy={false}
        protectedLexemeCount={1}
        onClose={onClose}
        onCaptureCurrentSelection={onCaptureCurrentSelection}
        onRemoveManualAnchor={onRemoveManualAnchor}
        onSubmitManualOffset={onSubmitManualOffset}
        onApplyDetectedOffset={vi.fn()}
        onOpenManualOffset={vi.fn()}
        onOpenJobLogs={vi.fn()}
      />,
    );

    expect(screen.getByTestId('offset-manual')).toBeTruthy();
    expect(screen.getByTestId('offset-manual-consensus').textContent).toContain('+1.500 s');
    expect(screen.getByText(/1 anchor/)).toBeTruthy();

    fireEvent.click(screen.getByTestId('offset-manual-capture'));
    fireEvent.click(screen.getByTestId('offset-manual-anchor-remove-1'));
    fireEvent.click(screen.getByTestId('offset-manual-submit'));

    expect(onCaptureCurrentSelection).toHaveBeenCalledOnce();
    expect(onRemoveManualAnchor).toHaveBeenCalledWith('1');
    expect(onSubmitManualOffset).toHaveBeenCalledOnce();
  });

  it('renders detecting and error phases with the expected progress and crash-log affordances', () => {
    const onOpenJobLogs = vi.fn();

    const { rerender } = render(
      <OffsetAdjustmentModal
        open
        offsetState={{ phase: 'detecting', jobId: 'offset-job-1', progress: 42, progressMessage: 'Scanning anchors…', origin: 'auto' }}
        manualAnchors={[]}
        manualConsensus={null}
        manualBusy={false}
        protectedLexemeCount={0}
        onClose={vi.fn()}
        onCaptureCurrentSelection={vi.fn()}
        onRemoveManualAnchor={vi.fn()}
        onSubmitManualOffset={vi.fn()}
        onApplyDetectedOffset={vi.fn()}
        onOpenManualOffset={vi.fn()}
        onOpenJobLogs={onOpenJobLogs}
      />,
    );

    expect(screen.getByTestId('offset-detecting')).toBeTruthy();
    expect(screen.getByText(/Scanning anchors/i)).toBeTruthy();

    rerender(
      <OffsetAdjustmentModal
        open
        offsetState={{ phase: 'error', message: 'Offset detection failed', jobId: 'offset-job-1' }}
        manualAnchors={[]}
        manualConsensus={null}
        manualBusy={false}
        protectedLexemeCount={0}
        onClose={vi.fn()}
        onCaptureCurrentSelection={vi.fn()}
        onRemoveManualAnchor={vi.fn()}
        onSubmitManualOffset={vi.fn()}
        onApplyDetectedOffset={vi.fn()}
        onOpenManualOffset={vi.fn()}
        onOpenJobLogs={onOpenJobLogs}
      />,
    );

    expect(screen.getByTestId('offset-error').textContent).toContain('Offset detection failed');
    fireEvent.click(screen.getByTestId('offset-error-view-log'));
    expect(onOpenJobLogs).toHaveBeenCalledWith('offset-job-1');
  });

  it('renders the detected review state with protected-lexeme notice and apply action', () => {
    const onApplyDetectedOffset = vi.fn();
    const onOpenManualOffset = vi.fn();

    render(
      <OffsetAdjustmentModal
        open
        offsetState={{ phase: 'detected', result: makeDetectedResult() }}
        manualAnchors={[]}
        manualConsensus={null}
        manualBusy={false}
        protectedLexemeCount={3}
        onClose={vi.fn()}
        onCaptureCurrentSelection={vi.fn()}
        onRemoveManualAnchor={vi.fn()}
        onSubmitManualOffset={vi.fn()}
        onApplyDetectedOffset={onApplyDetectedOffset}
        onOpenManualOffset={onOpenManualOffset}
        onOpenJobLogs={vi.fn()}
      />,
    );

    expect(screen.getByTestId('offset-value').textContent).toContain('+1.500 s');
    expect(screen.getByTestId('offset-protected-notice').textContent).toContain('3');

    fireEvent.click(screen.getByTestId('offset-use-known-anchor'));
    fireEvent.click(screen.getByTestId('offset-apply'));

    expect(onOpenManualOffset).toHaveBeenCalledOnce();
    expect(onApplyDetectedOffset).toHaveBeenCalledOnce();
  });
});
