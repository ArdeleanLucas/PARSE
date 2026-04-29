// @vitest-environment jsdom
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { OffsetDetectResult } from '../../api/client';
import { useOffsetState } from '../useOffsetState';

interface ConceptLike {
  id: number;
  key: string;
  name: string;
}

const selectedConcept: ConceptLike = { id: 1, key: '1', name: 'water' };

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

describe('useOffsetState', () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it('captures anchors from the current selection, marks the lexeme locked, and derives live consensus', () => {
    const markLexemeManuallyAdjusted = vi.fn();

    const { result } = renderHook(() =>
      useOffsetState({
        activeActionSpeaker: 'Fail01',
        selectedConcept,
        protectedLexemeCount: 1,
        getCurrentTime: () => 9.5,
        lookupConceptInterval: () => ({ start: 8, end: 8.4 }),
        markLexemeManuallyAdjusted,
        detectTimestampOffset: vi.fn(),
        detectTimestampOffsetFromPairs: vi.fn(),
        pollOffsetDetectJob: vi.fn(),
        applyTimestampOffset: vi.fn(),
        reloadSpeakerAnnotation: vi.fn(),
      }),
    );

    let capture;
    act(() => {
      capture = result.current.captureCurrentAnchor();
    });

    expect(capture).toEqual({
      ok: true,
      message: 'Anchored water @ 00:09.50 → +1.50s offset.',
    });
    expect(result.current.manualAnchors).toHaveLength(1);
    expect(result.current.manualAnchors[0]).toMatchObject({
      conceptKey: '1',
      conceptName: 'water',
      csvTimeSec: 8,
      audioTimeSec: 9.5,
    });
    expect(result.current.manualConsensus).toMatchObject({ median: 1.5, mad: 0 });
    expect(markLexemeManuallyAdjusted).toHaveBeenCalledWith('Fail01', 8, 8.4);

    act(() => {
      result.current.captureAnchorFromBar();
    });
    expect(result.current.captureToast).toContain('Anchored water @ 00:09.50');
  });

  it('submits captured anchors through the manual detect flow and preserves live progress updates', async () => {
    const detectTimestampOffsetFromPairs = vi.fn().mockResolvedValue({ jobId: 'offset-job-1', job_id: 'offset-job-1' });
    const pollOffsetDetectJob = vi.fn().mockImplementation(async (_jobId, _jobType, handlers) => {
      handlers?.onProgress?.({ progress: 42, message: 'Scanning anchors…' });
      return makeDetectedResult();
    });

    const { result } = renderHook(() =>
      useOffsetState({
        activeActionSpeaker: 'Fail01',
        selectedConcept,
        protectedLexemeCount: 0,
        getCurrentTime: () => 9.5,
        lookupConceptInterval: () => ({ start: 8, end: 8.4 }),
        markLexemeManuallyAdjusted: vi.fn(),
        detectTimestampOffset: vi.fn(),
        detectTimestampOffsetFromPairs,
        pollOffsetDetectJob,
        applyTimestampOffset: vi.fn(),
        reloadSpeakerAnnotation: vi.fn(),
      }),
    );

    act(() => {
      result.current.openManualOffset();
      result.current.captureCurrentAnchor();
    });

    await act(async () => {
      await result.current.submitManualOffset();
    });

    expect(detectTimestampOffsetFromPairs).toHaveBeenCalledWith('Fail01', [
      { audioTimeSec: 9.5, csvTimeSec: 8 },
    ]);
    expect(pollOffsetDetectJob).toHaveBeenCalledWith(
      'offset-job-1',
      'offset_detect_from_pair',
      expect.objectContaining({ onProgress: expect.any(Function) }),
    );
    expect(result.current.offsetState).toMatchObject({
      phase: 'detected',
      result: expect.objectContaining({ offsetSec: 1.5, method: 'manual_pair' }),
    });
    expect(result.current.lastProgressMessage).toBe('Scanning anchors…');
  });

  it('stores shifted concept counts after applying an offset', async () => {
    const applyTimestampOffset = vi.fn().mockResolvedValue({
      shiftedIntervals: 9358,
      shiftedConcepts: 521,
      protectedIntervals: 11,
      protectedLexemes: 1,
    });
    const reloadSpeakerAnnotation = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useOffsetState({
        activeActionSpeaker: 'Fail01',
        selectedConcept,
        protectedLexemeCount: 0,
        getCurrentTime: () => 9.5,
        lookupConceptInterval: () => ({ start: 8, end: 8.4 }),
        markLexemeManuallyAdjusted: vi.fn(),
        detectTimestampOffset: vi.fn(),
        detectTimestampOffsetFromPairs: vi.fn(),
        pollOffsetDetectJob: vi.fn(),
        applyTimestampOffset,
        reloadSpeakerAnnotation,
      }),
    );

    act(() => {
      result.current.setOffsetState({ phase: 'detected', result: makeDetectedResult({ offsetSec: 0.187 }) });
    });

    await act(async () => {
      await result.current.applyDetectedOffset();
    });

    expect(applyTimestampOffset).toHaveBeenCalledWith('Fail01', 0.187);
    expect(reloadSpeakerAnnotation).toHaveBeenCalledWith('Fail01');
    expect(result.current.offsetState).toMatchObject({
      phase: 'applied',
      shifted: 9358,
      shiftedConcepts: 521,
      protected: 1,
    });
  });
});
