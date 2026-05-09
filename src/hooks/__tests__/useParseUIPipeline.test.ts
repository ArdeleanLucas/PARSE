// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BatchSpeakerOutcome, UseBatchPipelineJobResult } from '../useBatchPipelineJob';
import { useParseUIPipeline } from '../useParseUIPipeline';
import type { TranscriptionRunConfirm } from '../../components/shared/TranscriptionRunModal';

vi.mock('../../api/client', () => ({
  pollCompute: vi.fn(),
  runLexemesByTag: vi.fn(),
}));

import { pollCompute, runLexemesByTag } from '../../api/client';

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
  beforeEach(() => {
    vi.mocked(pollCompute).mockReset();
    vi.mocked(runLexemesByTag).mockReset();
  });

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

  it('routes runMode tagged-only payload to runLexemesByTag instead of batch.run', async () => {
    const batch = makeBatchHandle();
    const closeRunModal = vi.fn();
    const reloadSpeakerAnnotation = vi.fn().mockResolvedValue(undefined);
    const loadEnrichments = vi.fn().mockResolvedValue(undefined);

    vi.mocked(runLexemesByTag).mockResolvedValue({ job_id: 'job-tagged-1', jobId: 'job-tagged-1' });
    vi.mocked(pollCompute).mockResolvedValue({
      status: 'complete',
      progress: 100,
      result: {
        resolved: {
          totalConcepts: 1,
          perSpeaker: { Alpha: { conceptCount: 1, concepts: [] } },
          unknownTags: [],
          ambiguousTags: {},
        },
        total: 2,
        results: [
          { speaker: 'Alpha', conceptId: 'c1', field: 'ortho', status: 'ok', text: 'x' },
          { speaker: 'Alpha', conceptId: 'c1', field: 'ipa', status: 'ok', text: 'y' },
        ],
      },
    });

    const confirm: TranscriptionRunConfirm = {
      speakers: ['Alpha'],
      steps: ['ortho', 'ipa'],
      overwrites: {},
      runMode: 'tagged-only',
      tagLabels: ['Thesis'],
      tagMatch: 'any',
      pad: 0.2,
    };

    const { result } = renderHook(() =>
      useParseUIPipeline({
        batch,
        closeRunModal,
        openBatchReport: vi.fn(),
        closeBatchReport: vi.fn(),
        isBatchReportOpen: false,
        getLanguage: () => 'ku',
        reloadSpeakerAnnotation,
        reloadStt: vi.fn(),
        loadEnrichments,
      }),
    );

    await act(async () => {
      await result.current.handleRunConfirm(confirm);
    });

    expect(closeRunModal).toHaveBeenCalledOnce();
    expect(batch.run).not.toHaveBeenCalled();
    expect(runLexemesByTag).toHaveBeenCalledTimes(1);
    expect(runLexemesByTag).toHaveBeenCalledWith({
      speakers: ['Alpha'],
      tagLabels: ['Thesis'],
      match: 'any',
      field: 'both',
      pad: 0.2,
    });
    expect(pollCompute).toHaveBeenCalledWith('lexemes_rerun_by_tag', 'job-tagged-1');
    expect(reloadSpeakerAnnotation).toHaveBeenCalledWith('Alpha');
    expect(loadEnrichments).toHaveBeenCalledOnce();
  });

  it('skips runLexemesByTag for tagged-only payloads with no tagLabels and no field-applicable steps', async () => {
    const batch = makeBatchHandle();
    vi.mocked(runLexemesByTag).mockClear();

    const { result } = renderHook(() =>
      useParseUIPipeline({
        batch,
        closeRunModal: vi.fn(),
        openBatchReport: vi.fn(),
        closeBatchReport: vi.fn(),
        isBatchReportOpen: false,
        getLanguage: () => undefined,
        reloadSpeakerAnnotation: vi.fn(),
        reloadStt: vi.fn(),
        loadEnrichments: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleRunConfirm({
        speakers: ['Alpha'],
        steps: ['stt'], // not ipa nor ortho — should bail out
        overwrites: {},
        runMode: 'tagged-only',
        tagLabels: ['Thesis'],
        tagMatch: 'any',
      });
    });

    expect(runLexemesByTag).not.toHaveBeenCalled();
    expect(batch.run).not.toHaveBeenCalled();
  });

  it('routes runLexemesByTag rejection to the user-facing error surface (synthetic outcomes + structured taggedOnlyError) and does NOT call batch.run', async () => {
    // Construct an ApiError-like rejection mirroring the upcoming Lane A
    // 400 contract (match=all with unknown labels). The hook must:
    //   1. Open the BatchReportModal (openBatchReport called once)
    //   2. Surface synthetic per-speaker error outcomes via displayedOutcomes
    //   3. Preserve the structured tagLabels[] from the response body in
    //      taggedOnlyError, NOT just stringify the message
    //   4. NOT silently swallow the failure (batch.run must not be called)
    const { ApiError } = await import('../../api/contracts/shared');
    const apiErr = new ApiError(
      400,
      'POST',
      '/api/lexemes/rerun-by-tag',
      { error: 'unknown tag labels in match=all', tagLabels: ['Phantom', 'Mystery'] },
      'API POST /api/lexemes/rerun-by-tag failed 400: ...',
    );
    vi.mocked(runLexemesByTag).mockRejectedValueOnce(apiErr);

    const batch = makeBatchHandle();
    const openBatchReport = vi.fn();
    const reloadSpeakerAnnotation = vi.fn();
    const loadEnrichments = vi.fn();

    const { result } = renderHook(() =>
      useParseUIPipeline({
        batch,
        closeRunModal: vi.fn(),
        openBatchReport,
        closeBatchReport: vi.fn(),
        isBatchReportOpen: false,
        getLanguage: () => 'ku',
        reloadSpeakerAnnotation,
        reloadStt: vi.fn(),
        loadEnrichments,
      }),
    );

    await act(async () => {
      await result.current.handleRunConfirm({
        speakers: ['Alpha', 'Beta'],
        steps: ['ortho', 'ipa'],
        overwrites: {},
        runMode: 'tagged-only',
        tagLabels: ['Phantom', 'Mystery'],
        tagMatch: 'all',
      });
    });

    expect(batch.run).not.toHaveBeenCalled();
    // Synthetic outcomes appear on displayedOutcomes (not on batch.state.outcomes
    // — the unmocked batch handle is left untouched).
    expect(result.current.displayedOutcomes.length).toBe(2);
    expect(result.current.displayedOutcomes.every((o) => o.status === 'error')).toBe(true);
    // The structured error payload preserves the actionable label list from
    // the body — NOT just an Error.message string.
    expect(result.current.taggedOnlyError).not.toBeNull();
    expect(result.current.taggedOnlyError!.status).toBe(400);
    expect(result.current.taggedOnlyError!.tagLabels).toEqual(['Phantom', 'Mystery']);
    // The modal opens so the user actually sees the failure.
    expect(openBatchReport).toHaveBeenCalledTimes(1);
    // No speaker reloads or enrichments fire on a hard rejection.
    expect(reloadSpeakerAnnotation).not.toHaveBeenCalled();
    expect(loadEnrichments).not.toHaveBeenCalled();
    // errorCount on the hook reflects the synthetic outcomes.
    expect(result.current.errorCount).toBe(2);
  });

  it('aggregates per-concept result rows by speaker so error and skip rows surface in displayedOutcomes', async () => {
    // Lane A may emit `statusCode` per row in a future contract. The hook
    // must aggregate ok/error/skip rows by speaker and field and expose
    // them on displayedOutcomes — not silently drop everything that is
    // not status === 'ok' (issue #2).
    vi.mocked(runLexemesByTag).mockResolvedValueOnce({ job_id: 'job-tagged-rows', jobId: 'job-tagged-rows' });
    vi.mocked(pollCompute).mockResolvedValueOnce({
      status: 'complete',
      progress: 100,
      result: {
        resolved: {
          totalConcepts: 3,
          perSpeaker: {
            Alpha: { conceptCount: 2, concepts: [] },
            Beta: { conceptCount: 1, concepts: [] },
          },
          unknownTags: [],
          ambiguousTags: {},
        },
        total: 4,
        results: [
          // Alpha — one ok ortho, one error ipa with statusCode 404
          { speaker: 'Alpha', conceptId: 'c1', field: 'ortho', status: 'ok', text: 'foo' },
          { speaker: 'Alpha', conceptId: 'c1', field: 'ipa', status: 'error', error: 'concept missing', statusCode: 404 } as never,
          // Beta — one skip
          { speaker: 'Beta', conceptId: 'c2', field: 'ortho', status: 'skip' },
        ],
      },
    });

    const batch = makeBatchHandle();
    const openBatchReport = vi.fn();
    const reloadSpeakerAnnotation = vi.fn().mockResolvedValue(undefined);
    const loadEnrichments = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useParseUIPipeline({
        batch,
        closeRunModal: vi.fn(),
        openBatchReport,
        closeBatchReport: vi.fn(),
        isBatchReportOpen: false,
        getLanguage: () => 'ku',
        reloadSpeakerAnnotation,
        reloadStt: vi.fn(),
        loadEnrichments,
      }),
    );

    await act(async () => {
      await result.current.handleRunConfirm({
        speakers: ['Alpha', 'Beta'],
        steps: ['ortho', 'ipa'],
        overwrites: {},
        runMode: 'tagged-only',
        tagLabels: ['Thesis'],
        tagMatch: 'any',
      });
    });

    expect(openBatchReport).toHaveBeenCalledTimes(1);
    // displayedOutcomes contains both speakers, with proper aggregated status.
    const byName = Object.fromEntries(
      result.current.displayedOutcomes.map((o) => [o.speaker, o]),
    );
    expect(byName.Alpha).toBeDefined();
    expect(byName.Beta).toBeDefined();
    expect(byName.Alpha.status).toBe('error');
    expect(byName.Beta.status).toBe('cancelled'); // only skip rows
    // counts roll up
    expect(result.current.errorCount).toBe(1);
    expect(result.current.completedCount).toBe(0);
    // The ok-row triggers a speaker reload; the error/skip-only speakers do not.
    expect(reloadSpeakerAnnotation).toHaveBeenCalledWith('Alpha');
    expect(reloadSpeakerAnnotation).not.toHaveBeenCalledWith('Beta');
  });
});
