// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockGetJobLogs = vi.fn();
vi.mock('../../api/client', () => ({
  getJobLogs: (...args: unknown[]) => mockGetJobLogs(...args),
}));

import { JobLogsModal } from './JobLogsModal';

describe('JobLogsModal', () => {
  beforeEach(() => {
    mockGetJobLogs.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders nothing open when jobId is null', () => {
    render(<JobLogsModal jobId={null} onClose={() => {}} />);
    expect(screen.queryByTestId('job-logs-modal')).toBeNull();
  });

  it('loads and renders job logs for an open job id', async () => {
    mockGetJobLogs.mockResolvedValue({
      error: 'boom',
      traceback: 'traceback-lines',
      stderrLog: 'stderr-lines',
      workerStderrLog: 'worker-lines',
    });

    render(<JobLogsModal jobId="job-123" onClose={() => {}} />);

    expect(screen.getByText(/job-123/i)).toBeTruthy();
    await waitFor(() => expect(mockGetJobLogs).toHaveBeenCalledWith('job-123'));
    expect(await screen.findByText('boom')).toBeTruthy();
    expect(screen.getByTestId('job-logs-traceback').textContent).toContain('traceback-lines');
    expect(screen.getByText(/per-job stderr/i)).toBeTruthy();
    expect(screen.getByText(/worker stderr tail/i)).toBeTruthy();
  });

  it('shows an error state and closes via the close button', async () => {
    const onClose = vi.fn();
    mockGetJobLogs.mockRejectedValue(new Error('network down'));

    render(<JobLogsModal jobId="job-456" onClose={onClose} />);

    expect(await screen.findByText(/failed to load logs: network down/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
