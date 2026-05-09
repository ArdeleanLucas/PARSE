import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TranscriptionRunConfirm } from '../components/shared/TranscriptionRunModal';
import { useBatchPipelineJob, type BatchSpeakerOutcome, type PipelineStepId, type UseBatchPipelineJobResult } from './useBatchPipelineJob';
import { pollCompute, runLexemesByTag } from '../api/client';
import { ApiError } from '../api/contracts/shared';
import type {
  LexemeRerunByTagField,
  LexemeRerunByTagResponse,
  LexemeRerunByTagResultEntry,
} from '../api/contracts/concepts';

type ScopedConceptRefreshTarget = { concept_id?: string; conceptId?: string; id?: string; start?: number; end?: number };

type ScopedPipelineResult = {
  run_mode?: string;
  runMode?: string;
  affected_concepts?: ScopedConceptRefreshTarget[];
  affectedConcepts?: ScopedConceptRefreshTarget[];
};

const PIPELINE_STEP_ORDER: PipelineStepId[] = ['normalize', 'stt', 'ortho', 'ipa'];

// === Tagged-only error surface ===
//
// Lane A's fix-up will return:
//   * 400 with body { error, tagLabels: string[] } when match=all has unknown labels
//   * 409 with body { error, tagLabels: string[], candidates?: Record<string, string[]> }
//     when ambiguous tags collide
//   * 200 with result.results rows that may carry { statusCode?: number } per row
//     so callers can distinguish 404 (concept not in registry) vs 500 (runner failure)
//
// We preserve that structured info verbatim so the UI surface (BatchReportModal +
// optional banner) can render actionable messages.
export interface TaggedOnlyRunError {
  status: number | null;
  message: string;
  tagLabels?: string[];
  candidates?: Record<string, string[]>;
  rawBody?: unknown;
}

export interface UseParseUIPipelineArgs {
  closeRunModal: () => void;
  openBatchReport: () => void;
  closeBatchReport: () => void;
  isBatchReportOpen: boolean;
  getLanguage: () => string | undefined;
  reloadSpeakerAnnotation: (speakerId: string) => Promise<void>;
  refreshScopedConceptRows?: (speakerId: string, targets: ScopedConceptRefreshTarget[]) => Promise<boolean> | boolean;
  reloadStt: (speakerId: string) => void;
  loadEnrichments: () => Promise<unknown> | unknown;
  batch?: UseBatchPipelineJobResult;
}

export interface UseParseUIPipelineResult {
  batch: UseBatchPipelineJobResult;
  reportStepsRun: PipelineStepId[];
  handleRunConfirm: (confirm: TranscriptionRunConfirm) => Promise<void>;
  handleRerunFailed: (speakers: string[]) => Promise<void>;
  showBatchCompleteBanner: boolean;
  completedCount: number;
  errorCount: number;
  cancelledCount: number;
  dismissBatchStatus: () => void;
  openBatchReport: () => void;
  /**
   * Outcomes the BatchReportModal should render. Falls back to batch.state.outcomes
   * for normal runs; switches to synthesized per-speaker outcomes when a tagged-only
   * run produced results (success or per-row errors) so error/skip rows are not
   * silently swallowed.
   */
  displayedOutcomes: BatchSpeakerOutcome[];
  /**
   * Top-level rejection from a tagged-only run (HTTP 400 unknown labels in ALL mode,
   * 409 ambiguous, or transport failure). Null when no error or when the most recent
   * tagged-only run succeeded.
   */
  taggedOnlyError: TaggedOnlyRunError | null;
  dismissTaggedOnlyError: () => void;
}

function buildRetryStepsBySpeaker(
  outcomes: BatchSpeakerOutcome[],
  speakers: string[],
  reportStepsRun: PipelineStepId[],
): Partial<Record<string, PipelineStepId[]>> {
  const stepsBySpeaker: Partial<Record<string, PipelineStepId[]>> = {};

  for (const outcome of outcomes) {
    if (!speakers.includes(outcome.speaker)) continue;
    if (outcome.result == null) {
      stepsBySpeaker[outcome.speaker] = reportStepsRun;
      continue;
    }
    const failedSteps = reportStepsRun.filter((step) => {
      const stepResult = outcome.result?.results[step];
      return stepResult?.status === 'error';
    });
    stepsBySpeaker[outcome.speaker] = failedSteps;
  }

  return stepsBySpeaker;
}

function collectRetrySteps(
  stepsBySpeaker: Partial<Record<string, PipelineStepId[]>>,
): PipelineStepId[] {
  const stepSet = new Set<PipelineStepId>();
  for (const steps of Object.values(stepsBySpeaker)) {
    for (const step of steps ?? []) stepSet.add(step);
  }
  return Array.from(stepSet).sort(
    (a, b) => PIPELINE_STEP_ORDER.indexOf(a) - PIPELINE_STEP_ORDER.indexOf(b),
  );
}

function scopedConceptTargets(result: unknown): ScopedConceptRefreshTarget[] | null {
  if (!result || typeof result !== 'object') return null;
  const payload = result as ScopedPipelineResult;
  const mode = payload.run_mode ?? payload.runMode;
  if (mode !== 'concept-windows' && mode !== 'edited-only') return null;
  const targets = payload.affected_concepts ?? payload.affectedConcepts;
  return Array.isArray(targets) ? targets : [];
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

const TAGGED_ONLY_COMPUTE_TYPE = 'lexemes_rerun_by_tag';
const TAGGED_ONLY_POLL_INTERVAL_MS = 750;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => { window.setTimeout(resolve, ms); });
}

function buildTaggedOnlyError(err: unknown): TaggedOnlyRunError {
  if (err instanceof ApiError) {
    const body = err.body;
    let tagLabels: string[] | undefined;
    let candidates: Record<string, string[]> | undefined;
    let bodyMessage: string | undefined;
    if (isPlainRecord(body)) {
      const labels = body.tagLabels;
      if (Array.isArray(labels)) {
        tagLabels = labels.filter((x): x is string => typeof x === 'string');
      }
      const cands = body.candidates;
      if (isPlainRecord(cands)) {
        const out: Record<string, string[]> = {};
        for (const [k, v] of Object.entries(cands)) {
          if (Array.isArray(v)) {
            out[k] = v.filter((x): x is string => typeof x === 'string');
          }
        }
        candidates = out;
      }
      const msg = body.error ?? body.message;
      if (typeof msg === 'string') bodyMessage = msg;
    }
    return {
      status: err.status,
      message: bodyMessage ?? err.message,
      tagLabels,
      candidates,
      rawBody: body,
    };
  }
  return {
    status: null,
    message: err instanceof Error ? err.message : String(err ?? 'Tagged-only run failed'),
  };
}

function coerceTaggedOnlyJobResult(result: unknown, jobId: string): LexemeRerunByTagResponse {
  if (!isPlainRecord(result)) {
    throw new Error('Tagged-only compute completed without a result payload');
  }
  const rows = Array.isArray(result.results)
    ? (result.results as LexemeRerunByTagResultEntry[])
    : [];
  return {
    jobId,
    resolved: result.resolved as LexemeRerunByTagResponse['resolved'],
    total: typeof result.total === 'number' ? result.total : rows.length,
    results: rows,
  };
}

async function pollTaggedOnlyJob(jobId: string): Promise<LexemeRerunByTagResponse> {
  for (;;) {
    const status = await pollCompute(TAGGED_ONLY_COMPUTE_TYPE, jobId);
    const normalizedStatus = status.status.toLowerCase();
    if (normalizedStatus === 'complete' || normalizedStatus === 'completed' || normalizedStatus === 'success') {
      return coerceTaggedOnlyJobResult(status.result, jobId);
    }
    if (normalizedStatus === 'error' || normalizedStatus === 'failed' || normalizedStatus === 'cancelled') {
      throw new Error(status.error ?? status.message ?? `Tagged-only compute ${normalizedStatus}`);
    }
    await sleep(TAGGED_ONLY_POLL_INTERVAL_MS);
  }
}

interface TaggedOnlyResultRowExt extends LexemeRerunByTagResultEntry {
  statusCode?: number;
}

function aggregateTaggedOnlyOutcomes(
  speakers: string[],
  rows: TaggedOnlyResultRowExt[],
): BatchSpeakerOutcome[] {
  const speakerOrder: string[] = [];
  const seen = new Set<string>();
  for (const sp of speakers) {
    if (!seen.has(sp)) { speakerOrder.push(sp); seen.add(sp); }
  }
  for (const row of rows) {
    if (!seen.has(row.speaker)) { speakerOrder.push(row.speaker); seen.add(row.speaker); }
  }

  return speakerOrder.map((speaker) => {
    const speakerRows = rows.filter((r) => r.speaker === speaker);
    if (speakerRows.length === 0) {
      // No work at all for this speaker (e.g. zero matched concepts).
      return {
        speaker,
        status: 'cancelled',
        error: null,
        result: null,
      };
    }
    const errorRows = speakerRows.filter((r) => r.status === 'error');
    const okRows = speakerRows.filter((r) => r.status === 'ok');
    const skipRows = speakerRows.filter((r) => r.status === 'skip');

    const results: BatchSpeakerOutcome['result'] extends infer R ? R : never =
      {} as never;
    // Build a synthetic PipelineRunResult with one entry per field that
    // had any row. Aggregate status: ok if any ok, else error if any error,
    // else skipped.
    const fieldStatus: Partial<Record<'ortho' | 'ipa', { status: 'ok' | 'error' | 'skipped'; details: string }>> = {};
    for (const row of speakerRows) {
      const f = row.field;
      const cur = fieldStatus[f];
      const nextStatus = row.status === 'ok' ? 'ok' : row.status === 'error' ? 'error' : 'skipped';
      if (!cur) {
        fieldStatus[f] = { status: nextStatus, details: row.error ?? row.text ?? '' };
      } else if (nextStatus === 'error' && cur.status !== 'error') {
        fieldStatus[f] = { status: 'error', details: row.error ?? cur.details };
      } else if (nextStatus === 'ok' && cur.status === 'skipped') {
        fieldStatus[f] = { status: 'ok', details: row.text ?? cur.details };
      }
    }
    const stepsRunDeduped: PipelineStepId[] = [];
    for (const f of ['ortho', 'ipa'] as const) {
      if (fieldStatus[f]) {
        stepsRunDeduped.push(f);
        (results as Record<string, unknown>)[f] = {
          status: fieldStatus[f]!.status,
          // Pass through error text as `error` so existing report cells render it.
          ...(fieldStatus[f]!.status === 'error' ? { error: fieldStatus[f]!.details } : {}),
        };
      }
    }

    const summary = {
      ok: okRows.length,
      skipped: skipRows.length,
      error: errorRows.length,
    };
    const status: BatchSpeakerOutcome['status'] = errorRows.length > 0
      ? 'error'
      : okRows.length > 0
        ? 'complete'
        : 'cancelled';
    const errorMsg = errorRows.length > 0
      ? `${errorRows.length} concept row(s) errored` +
        (errorRows[0].statusCode != null ? ` (first status ${errorRows[0].statusCode})` : '')
      : null;

    return {
      speaker,
      status,
      error: errorMsg,
      result: {
        speaker,
        steps_run: stepsRunDeduped,
        results: results as never,
        summary,
        run_mode: 'tagged-only' as unknown as 'full',
      } as never,
    };
  });
}

export function useParseUIPipeline({
  closeRunModal,
  openBatchReport,
  closeBatchReport,
  isBatchReportOpen,
  getLanguage,
  reloadSpeakerAnnotation,
  refreshScopedConceptRows,
  reloadStt,
  loadEnrichments,
  batch: injectedBatch,
}: UseParseUIPipelineArgs): UseParseUIPipelineResult {
  const ownedBatch = useBatchPipelineJob();
  const batch = injectedBatch ?? ownedBatch;
  const [reportStepsRun, setReportStepsRun] = useState<PipelineStepId[]>([]);
  const [taggedOnlyOutcomes, setTaggedOnlyOutcomes] = useState<BatchSpeakerOutcome[] | null>(null);
  const [taggedOnlyError, setTaggedOnlyError] = useState<TaggedOnlyRunError | null>(null);
  const previousBatchStatusRef = useRef<typeof batch.state.status>(batch.state.status);

  useEffect(() => {
    if (previousBatchStatusRef.current === 'running' && batch.state.status === 'complete') {
      openBatchReport();
      void (async () => {
        for (const outcome of batch.state.outcomes) {
          if (outcome.status === 'complete') {
            reloadStt(outcome.speaker);
            const targets = scopedConceptTargets(outcome.result);
            if (targets && refreshScopedConceptRows) {
              // Best-effort in-place patch for retiming-only outcomes; this
              // cannot gate the disk reload because concept-window backends
              // can return only affected_concepts boundary metadata without
              // the new tier intervals, making no-op concept-tier rewrites
              // look like a successful in-memory tier refresh.
              await refreshScopedConceptRows(outcome.speaker, targets);
            }
            await reloadSpeakerAnnotation(outcome.speaker);
          }
        }
        await loadEnrichments();
      })();
    }
    previousBatchStatusRef.current = batch.state.status;
  }, [batch.state.status, batch.state.outcomes, loadEnrichments, openBatchReport, refreshScopedConceptRows, reloadSpeakerAnnotation, reloadStt]);

  const handleRunConfirm = useCallback(async (confirm: TranscriptionRunConfirm) => {
    closeRunModal();
    setReportStepsRun(confirm.steps);
    if (confirm.speakers.length === 0 || confirm.steps.length === 0) return;

    if (confirm.runMode === 'tagged-only') {
      const tagLabels = (confirm.tagLabels ?? []).slice();
      if (tagLabels.length === 0) return;
      const stepsArr = confirm.steps;
      const wantsIpa = stepsArr.includes('ipa');
      const wantsOrtho = stepsArr.includes('ortho');
      const field: LexemeRerunByTagField | null = wantsIpa && wantsOrtho
        ? 'both'
        : wantsIpa
          ? 'ipa'
          : wantsOrtho
            ? 'ortho'
            : null;
      if (field === null) return;
      const payload = {
        speakers: confirm.speakers,
        tagLabels,
        match: confirm.tagMatch ?? 'any',
        field,
        ...(confirm.pad === undefined ? {} : { pad: confirm.pad as number }),
      };
      // Reset prior tagged-only state before issuing the new request.
      setTaggedOnlyOutcomes(null);
      setTaggedOnlyError(null);
      let result: LexemeRerunByTagResponse | null = null;
      try {
        const job = await runLexemesByTag(payload);
        result = await pollTaggedOnlyJob(job.jobId ?? job.job_id);
      } catch (err) {
        // Surface to the BatchReportModal as a synthetic per-request error
        // outcome AND populate the structured taggedOnlyError so the host
        // can render a banner with actionable label/candidate detail.
        const structured = buildTaggedOnlyError(err);
        console.error('[useParseUIPipeline] runLexemesByTag failed', err);
        const syntheticOutcome: BatchSpeakerOutcome[] = confirm.speakers.map((speaker) => ({
          speaker,
          status: 'error',
          error: structured.message,
          result: null,
        }));
        setTaggedOnlyOutcomes(syntheticOutcome);
        setTaggedOnlyError(structured);
        openBatchReport();
        return;
      }
      const rows = (result.results ?? []) as TaggedOnlyResultRowExt[];
      const outcomes = aggregateTaggedOnlyOutcomes(confirm.speakers, rows);
      setTaggedOnlyOutcomes(outcomes);
      setTaggedOnlyError(null);
      // Log per-row errors for debugging even though the modal carries them.
      const errorRows = rows.filter((r) => r.status === 'error');
      if (errorRows.length > 0) {
        console.warn('[useParseUIPipeline] tagged-only run errored rows', errorRows);
      }
      // Fire UI refresh side-effects for speakers that produced any ok row.
      const affectedSpeakers = new Set<string>();
      for (const row of rows) {
        if (row.status === 'ok') affectedSpeakers.add(row.speaker);
      }
      for (const speaker of affectedSpeakers) {
        await reloadSpeakerAnnotation(speaker);
      }
      await loadEnrichments();
      // Always surface the report so error/skip rows are visible even when
      // no speaker had an `ok` row.
      openBatchReport();
      return;
    }

    // Non-tagged-only runs: clear any prior tagged-only state so the report
    // modal goes back to displaying batch outcomes.
    setTaggedOnlyOutcomes(null);
    setTaggedOnlyError(null);

    await batch.run({
      speakers: confirm.speakers,
      steps: confirm.steps,
      overwrites: confirm.overwrites,
      language: getLanguage(),
      refineLexemes: confirm.refineLexemes,
      runMode: confirm.runMode,
      pad: confirm.pad,
    });
  }, [batch, closeRunModal, getLanguage, loadEnrichments, openBatchReport, reloadSpeakerAnnotation]);

  const handleRerunFailed = useCallback(async (speakers: string[]) => {
    if (speakers.length === 0 || reportStepsRun.length === 0) return;

    const stepsBySpeaker = buildRetryStepsBySpeaker(batch.state.outcomes, speakers, reportStepsRun);
    const steps = collectRetrySteps(stepsBySpeaker);
    if (steps.length === 0) return;

    closeBatchReport();
    await batch.run({
      speakers,
      steps,
      stepsBySpeaker,
      overwrites: steps.reduce<Partial<Record<PipelineStepId, boolean>>>((acc, step) => {
        acc[step] = true;
        return acc;
      }, {}),
      language: getLanguage(),
    });
  }, [batch, closeBatchReport, getLanguage, reportStepsRun]);

  const displayedOutcomes = useMemo<BatchSpeakerOutcome[]>(
    () => taggedOnlyOutcomes ?? batch.state.outcomes,
    [taggedOnlyOutcomes, batch.state.outcomes],
  );

  const completedCount = useMemo(
    () => displayedOutcomes.filter((outcome) => outcome.status === 'complete').length,
    [displayedOutcomes],
  );
  const errorCount = useMemo(
    () => displayedOutcomes.filter((outcome) => outcome.status === 'error').length,
    [displayedOutcomes],
  );
  const cancelledCount = useMemo(
    () => displayedOutcomes.filter((outcome) => outcome.status === 'cancelled').length,
    [displayedOutcomes],
  );

  const dismissTaggedOnlyError = useCallback(() => {
    setTaggedOnlyError(null);
  }, []);

  const dismissBatchStatus = useCallback(() => {
    setTaggedOnlyOutcomes(null);
    setTaggedOnlyError(null);
    batch.reset();
  }, [batch]);

  return {
    batch,
    reportStepsRun,
    handleRunConfirm,
    handleRerunFailed,
    showBatchCompleteBanner: batch.state.status === 'complete' && !isBatchReportOpen,
    completedCount,
    errorCount,
    cancelledCount,
    dismissBatchStatus,
    openBatchReport,
    displayedOutcomes,
    taggedOnlyError,
    dismissTaggedOnlyError,
  };
}

export { buildRetryStepsBySpeaker, collectRetrySteps };
