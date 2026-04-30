// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { BatchSpeakerOutcome, UseBatchPipelineJobResult } from '../useBatchPipelineJob';
import { useParseUIPipeline } from '../useParseUIPipeline';
import type { TranscriptionRunConfirm } from '../../components/shared/TranscriptionRunModal';

function makeBatchHandle(
  overrides: Partial<UseBatchPipelineJobResult['state']> = {},
): UseBatchPipelineJobResult {
  return {
    state: {
      status: 'idle',
      cancelled: false,
      totalSpeakers: 0,
      completedSpeakers: 0,
      currentSpeakerIndex: null,
      currentSpeaker: null,
      currentSubJobId: null,
      currentProgress: 0,
      currentMessage: null,
      outcomes: [],
      ...overrides,
    },
    run: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn(),
    reset: vi.fn(),
  };
}

describe('useParseUIPipeline', () => {
  it('closes the run modal and dispatches batch.run with the selected transcription payload', async () => {
    const batch = makeBatchHandle();
    const closeRunModal = vi.fn();
    const confirm: TranscriptionRunConfirm = {
      speakers: ['Fail01'],
      steps: ['normalize', 'stt'],
      overwrites: { stt: true },
      refineLexemes: true,
      runMode: 'concept-windows',
    };

    const { result } = renderHook(() =>
      useParseUIPipeline({
        batch,
        closeRunModal,
        openBatchReport: vi.fn(),
        closeBatchReport: vi.fn(),
        isBatchReportOpen: false,
        getLanguage: () => 'ku',
        reloadSpeakerAnnotation: vi.fn(),
        reloadStt: vi.fn(),
        loadEnrichments: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleRunConfirm(confirm);
    });

    expect(closeRunModal).toHaveBeenCalledOnce();
    expect(result.current.reportStepsRun).toEqual(['normalize', 'stt']);
    expect(batch.run).toHaveBeenCalledWith({
      speakers: ['Fail01'],
      steps: ['normalize', 'stt'],
      overwrites: { stt: true },
      language: 'ku',
      refineLexemes: true,
      runMode: 'concept-windows',
    });
  });

  it('reruns only failed steps per speaker and forces overwrite for the retry set', async () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: 'Fail01',
        status: 'error',
        error: 'boom',
        result: {
          speaker: 'Fail01',
          steps_run: ['normalize', 'stt', 'ipa'],
          results: {
            normalize: { status: 'ok' },
            stt: { status: 'error' },
            ipa: { status: 'error' },
          },
          summary: { ok: 1, skipped: 0, error: 2 },
        },
      },
      {
        speaker: 'Kalh01',
        status: 'error',
        error: 'transport',
        result: null,
      },
    ];
    const batch = makeBatchHandle({ status: 'complete', outcomes });
    const closeBatchReport = vi.fn();

    const { result } = renderHook(() =>
      useParseUIPipeline({
        batch,
        closeRunModal: vi.fn(),
        openBatchReport: vi.fn(),
        closeBatchReport,
        isBatchReportOpen: true,
        getLanguage: () => 'ku',
        reloadSpeakerAnnotation: vi.fn(),
        reloadStt: vi.fn(),
        loadEnrichments: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleRunConfirm({
        speakers: ['Fail01', 'Kalh01'],
        steps: ['normalize', 'stt', 'ipa'],
        overwrites: {},
        runMode: 'full',
      });
    });
    vi.mocked(batch.run).mockClear();

    await act(async () => {
      await result.current.handleRerunFailed(['Fail01', 'Kalh01']);
    });

    expect(closeBatchReport).toHaveBeenCalledOnce();
    expect(batch.run).toHaveBeenCalledWith({
      speakers: ['Fail01', 'Kalh01'],
      steps: ['stt', 'ipa', 'normalize'].sort((a, b) => ['normalize', 'stt', 'ortho', 'ipa'].indexOf(a) - ['normalize', 'stt', 'ortho', 'ipa'].indexOf(b)),
      stepsBySpeaker: {
        Fail01: ['stt', 'ipa'],
        Kalh01: ['normalize', 'stt', 'ipa'],
      },
      overwrites: {
        normalize: true,
        stt: true,
        ipa: true,
      },
      language: 'ku',
    });
  });

  it('reloads speaker annotation even when scoped concept-row refresh succeeds', async () => {
    const openBatchReport = vi.fn();
    const reloadStt = vi.fn();
    const reloadSpeakerAnnotation = vi.fn().mockResolvedValue(undefined);
    const refreshScopedConceptRows = vi.fn().mockResolvedValue(true);
    const loadEnrichments = vi.fn().mockResolvedValue(undefined);

    const runningBatch = makeBatchHandle({
      status: 'running',
      outcomes: [{ speaker: 'Fail01', status: 'running', error: null, result: null }],
    });
    const completedBatch = makeBatchHandle({
      status: 'complete',
      outcomes: [
        {
          speaker: 'Fail01',
          status: 'complete',
          error: null,
          result: {
            speaker: 'Fail01',
            steps_run: ['stt', 'ortho'],
            results: { stt: { status: 'ok' }, ortho: { status: 'ok' } },
            summary: { ok: 2, skipped: 0, error: 0 },
            run_mode: 'edited-only',
            affected_concepts: [
              { concept_id: '2', start: 5, end: 6 },
              { concept_id: '7', start: 10, end: 11 },
            ],
          },
        },
      ],
    });

    const { rerender } = renderHook(
      ({ batch }) =>
        useParseUIPipeline({
          batch,
          closeRunModal: vi.fn(),
          openBatchReport,
          closeBatchReport: vi.fn(),
          isBatchReportOpen: false,
          getLanguage: () => undefined,
          reloadSpeakerAnnotation,
          reloadStt,
          loadEnrichments,
          refreshScopedConceptRows,
        }),
      { initialProps: { batch: runningBatch } },
    );

    rerender({ batch: completedBatch });

    await waitFor(() => expect(openBatchReport).toHaveBeenCalledOnce());
    await waitFor(() => expect(refreshScopedConceptRows).toHaveBeenCalledWith('Fail01', [
      { concept_id: '2', start: 5, end: 6 },
      { concept_id: '7', start: 10, end: 11 },
    ]));
    await waitFor(() => expect(reloadSpeakerAnnotation).toHaveBeenCalledWith('Fail01'));
    expect(refreshScopedConceptRows.mock.invocationCallOrder[0]).toBeLessThan(
      reloadSpeakerAnnotation.mock.invocationCallOrder[0],
    );
    expect(reloadStt).toHaveBeenCalledWith('Fail01');
    expect(loadEnrichments).toHaveBeenCalledOnce();
  });

  it('opens the batch report and refreshes completed speakers when the batch transitions from running to complete', async () => {
    const openBatchReport = vi.fn();
    const reloadStt = vi.fn();
    const reloadSpeakerAnnotation = vi.fn().mockResolvedValue(undefined);
    const loadEnrichments = vi.fn().mockResolvedValue(undefined);

    const runningBatch = makeBatchHandle({
      status: 'running',
      outcomes: [{ speaker: 'Fail01', status: 'running', error: null, result: null }],
    });
    const completedBatch = makeBatchHandle({
      status: 'complete',
      outcomes: [
        {
          speaker: 'Fail01',
          status: 'complete',
          error: null,
          result: {
            speaker: 'Fail01',
            steps_run: ['stt'],
            results: { stt: { status: 'ok' } },
            summary: { ok: 1, skipped: 0, error: 0 },
          },
        },
        { speaker: 'Fail02', status: 'error', error: 'boom', result: null },
      ],
    });

    const { rerender, result } = renderHook(
      ({ batch }) =>
        useParseUIPipeline({
          batch,
          closeRunModal: vi.fn(),
          openBatchReport,
          closeBatchReport: vi.fn(),
          isBatchReportOpen: false,
          getLanguage: () => undefined,
          reloadSpeakerAnnotation,
          reloadStt,
          loadEnrichments,
        }),
      { initialProps: { batch: runningBatch } },
    );

    rerender({ batch: completedBatch });

    await waitFor(() => expect(openBatchReport).toHaveBeenCalledOnce());
    await waitFor(() => expect(reloadSpeakerAnnotation).toHaveBeenCalledWith('Fail01'));
    expect(reloadStt).toHaveBeenCalledWith('Fail01');
    expect(loadEnrichments).toHaveBeenCalledOnce();
    expect(result.current.showBatchCompleteBanner).toBe(true);
    expect(result.current.completedCount).toBe(1);
    expect(result.current.errorCount).toBe(1);
  });
});
