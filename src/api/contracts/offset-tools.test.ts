import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ComputeStatus } from '../types';
import { pollOffsetDetectJob } from './offset-tools';
import { pollCompute } from './chat-and-generic-compute';

vi.mock('./chat-and-generic-compute', () => ({
  pollCompute: vi.fn(),
}));

function runningStatus(index: number): ComputeStatus {
  return {
    status: 'running',
    progress: index,
    message: `Still running ${index}`,
  };
}

describe('pollOffsetDetectJob', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it('keeps polling long-running offset detection until the backend reports completion', async () => {
    let now = 0;
    vi.spyOn(Date, 'now').mockImplementation(() => {
      now += 10;
      return now;
    });

    const pollMock = vi.mocked(pollCompute);
    for (let i = 0; i < 50; i += 1) {
      pollMock.mockResolvedValueOnce(runningStatus(i));
    }
    pollMock.mockResolvedValueOnce({
      status: 'complete',
      progress: 100,
      result: {
        speaker: 'Fail01',
        offsetSec: 1.25,
        confidence: 0.91,
        nAnchors: 2,
        totalAnchors: 2,
        totalSegments: 12,
        method: 'auto',
      },
    });

    await expect(
      pollOffsetDetectJob('offset-job-long', 'offset_detect', { intervalMs: 0, timeoutMs: 50 }),
    ).resolves.toMatchObject({ speaker: 'Fail01', offsetSec: 1.25 });
    expect(pollMock).toHaveBeenCalledTimes(51);
  });
});
