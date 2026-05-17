// @vitest-environment jsdom
import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { OffsetDetectResult } from '../../api/client';
import { OffsetJobError } from '../../api/client';
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

  it('captures anchors from the current selection without marking the lexeme locked, and derives live consensus', () => {
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
    expect(markLexemeManuallyAdjusted).not.toHaveBeenCalled();

    act(() => {
      result.current.captureAnchorFromBar();
    });
    expect(result.current.captureToast).toContain('Anchored water @ 00:09.50');
    expect(markLexemeManuallyAdjusted).not.toHaveBeenCalled();
  });

  it('uses imported CSV provenance for manual anchor truth after a lexeme was retimed', () => {
    const { result } = renderHook(() =>
      useOffsetState({
        activeActionSpeaker: 'Fail01',
        selectedConcept,
        protectedLexemeCount: 0,
        getCurrentTime: () => 78.0,
        lookupConceptInterval: () => ({
          start: 78.0,
          end: 78.5,
          imported_csv_start: 1.3,
          imported_csv_end: 1.8,
        }),
        markLexemeManuallyAdjusted: vi.fn(),
        detectTimestampOffset: vi.fn(),
        detectTimestampOffsetFromPairs: vi.fn(),
        pollOffsetDetectJob: vi.fn(),
        applyTimestampOffset: vi.fn(),
        reloadSpeakerAnnotation: vi.fn(),
        flushAutosave: vi.fn(),
      }),
    );

    act(() => {
      result.current.captureCurrentAnchor();
    });

    expect(result.current.manualAnchors[0]).toMatchObject({
      conceptKey: '1',
      conceptName: 'water',
      csvTimeSec: 1.3,
      audioTimeSec: 78.0,
    });
    expect(result.current.manualConsensus?.median).toBeCloseTo(76.7);
    expect(result.current.manualConsensus?.mad).toBe(0);
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

  it('marks surviving manual anchors only after applying a detected offset', async () => {
    const secondConcept: ConceptLike = { id: 2, key: '2', name: 'fire' };
    const intervals: Record<string, { start: number; end: number }> = {
      '1': { start: 8, end: 8.4 },
      '2': { start: 10, end: 10.4 },
    };
    const markLexemeManuallyAdjusted = vi.fn();
    const detectTimestampOffsetFromPairs = vi.fn().mockResolvedValue({ jobId: 'offset-job-anchors' });
    const pollOffsetDetectJob = vi.fn().mockResolvedValue(makeDetectedResult({ offsetSec: 2.25, nAnchors: 2, totalAnchors: 2 }));
    const applyTimestampOffset = vi.fn().mockResolvedValue({ shiftedIntervals: 2, protectedLexemes: 0 });
    const reloadSpeakerAnnotation = vi.fn().mockResolvedValue(undefined);

    const { result, rerender } = renderHook(
      ({ concept, time }: { concept: ConceptLike; time: number }) =>
        useOffsetState({
          activeActionSpeaker: 'Fail01',
          selectedConcept: concept,
          protectedLexemeCount: 0,
          getCurrentTime: () => time,
          lookupConceptInterval: (_speaker, conceptArg) => intervals[conceptArg.key] ?? null,
          markLexemeManuallyAdjusted,
          detectTimestampOffset: vi.fn(),
          detectTimestampOffsetFromPairs,
          pollOffsetDetectJob,
          applyTimestampOffset,
          reloadSpeakerAnnotation,
        }),
      { initialProps: { concept: selectedConcept, time: 9.5 } },
    );

    act(() => {
      result.current.captureCurrentAnchor();
    });
    rerender({ concept: secondConcept, time: 12.5 });
    act(() => {
      result.current.captureCurrentAnchor();
    });
    expect(markLexemeManuallyAdjusted).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.submitManualOffset();
    });
    await act(async () => {
      await result.current.applyDetectedOffset();
    });

    expect(applyTimestampOffset).toHaveBeenCalledWith('Fail01', 2.25);
    expect(markLexemeManuallyAdjusted.mock.calls).toEqual([
      ['Fail01', 8, 8.4],
      ['Fail01', 10, 10.4],
    ]);
    expect(reloadSpeakerAnnotation).toHaveBeenCalledWith('Fail01');
  });

  it('does not mark anchors removed before applying an offset', async () => {
    const secondConcept: ConceptLike = { id: 2, key: '2', name: 'fire' };
    const intervals: Record<string, { start: number; end: number }> = {
      '1': { start: 8, end: 8.4 },
      '2': { start: 10, end: 10.4 },
    };
    const markLexemeManuallyAdjusted = vi.fn();
    const detectTimestampOffsetFromPairs = vi.fn().mockResolvedValue({ jobId: 'offset-job-anchors' });
    const pollOffsetDetectJob = vi.fn().mockResolvedValue(makeDetectedResult({ offsetSec: 2.25, nAnchors: 1, totalAnchors: 1 }));
    const applyTimestampOffset = vi.fn().mockResolvedValue({ shiftedIntervals: 2, protectedLexemes: 0 });

    const { result, rerender } = renderHook(
      ({ concept, time }: { concept: ConceptLike; time: number }) =>
        useOffsetState({
          activeActionSpeaker: 'Fail01',
          selectedConcept: concept,
          protectedLexemeCount: 0,
          getCurrentTime: () => time,
          lookupConceptInterval: (_speaker, conceptArg) => intervals[conceptArg.key] ?? null,
          markLexemeManuallyAdjusted,
          detectTimestampOffset: vi.fn(),
          detectTimestampOffsetFromPairs,
          pollOffsetDetectJob,
          applyTimestampOffset,
          reloadSpeakerAnnotation: vi.fn().mockResolvedValue(undefined),
        }),
      { initialProps: { concept: selectedConcept, time: 9.5 } },
    );

    act(() => {
      result.current.captureCurrentAnchor();
    });
    rerender({ concept: secondConcept, time: 12.5 });
    act(() => {
      result.current.captureCurrentAnchor();
      result.current.removeManualAnchor('1');
    });
    expect(result.current.manualAnchors).toHaveLength(1);
    expect(markLexemeManuallyAdjusted).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.submitManualOffset();
    });
    await act(async () => {
      await result.current.applyDetectedOffset();
    });

    expect(markLexemeManuallyAdjusted.mock.calls).toEqual([
      ['Fail01', 10, 10.4],
    ]);
    expect(markLexemeManuallyAdjusted).not.toHaveBeenCalledWith('Fail01', 8, 8.4);
  });
  it('marks backend offset-detect errors as backend failures with propagated messages', async () => {
    const pollOffsetDetectJob = vi.fn().mockRejectedValue(
      new OffsetJobError('offset-job-error', 'Backend failed while detecting offset', 'traceback body'),
    );

    const { result } = renderHook(() =>
      useOffsetState({
        activeActionSpeaker: 'Fail01',
        selectedConcept,
        protectedLexemeCount: 0,
        getCurrentTime: () => 9.5,
        lookupConceptInterval: () => ({ start: 8, end: 8.4 }),
        markLexemeManuallyAdjusted: vi.fn(),
        detectTimestampOffset: vi.fn().mockResolvedValue({ jobId: 'offset-job-error' }),
        detectTimestampOffsetFromPairs: vi.fn(),
        pollOffsetDetectJob,
        applyTimestampOffset: vi.fn(),
        reloadSpeakerAnnotation: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.detectOffsetForSpeaker();
    });

    expect(result.current.offsetState).toMatchObject({
      phase: 'error',
      jobId: 'offset-job-error',
      message: 'Backend failed while detecting offset',
      traceback: 'traceback body',
      isBackendFailure: true,
    });
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
