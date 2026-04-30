import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TranscriptionRunConfirm } from '../components/shared/TranscriptionRunModal';
import { useBatchPipelineJob, type BatchSpeakerOutcome, type PipelineStepId, type UseBatchPipelineJobResult } from './useBatchPipelineJob';

type ScopedConceptRefreshTarget = { concept_id?: string; conceptId?: string; id?: string; start?: number; end?: number };

type ScopedPipelineResult = {
  run_mode?: string;
  runMode?: string;
  affected_concepts?: ScopedConceptRefreshTarget[];
  affectedConcepts?: ScopedConceptRefreshTarget[];
};

const PIPELINE_STEP_ORDER: PipelineStepId[] = ['normalize', 'stt', 'ortho', 'ipa'];

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
    await batch.run({
      speakers: confirm.speakers,
      steps: confirm.steps,
      overwrites: confirm.overwrites,
      language: getLanguage(),
      refineLexemes: confirm.refineLexemes,
      runMode: confirm.runMode,
    });
  }, [batch, closeRunModal, getLanguage]);

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

  const completedCount = useMemo(
    () => batch.state.outcomes.filter((outcome) => outcome.status === 'complete').length,
    [batch.state.outcomes],
  );
  const errorCount = useMemo(
    () => batch.state.outcomes.filter((outcome) => outcome.status === 'error').length,
    [batch.state.outcomes],
  );
  const cancelledCount = useMemo(
    () => batch.state.outcomes.filter((outcome) => outcome.status === 'cancelled').length,
    [batch.state.outcomes],
  );

  return {
    batch,
    reportStepsRun,
    handleRunConfirm,
    handleRerunFailed,
    showBatchCompleteBanner: batch.state.status === 'complete' && !isBatchReportOpen,
    completedCount,
    errorCount,
    cancelledCount,
    dismissBatchStatus: batch.reset,
    openBatchReport,
  };
}

export { buildRetryStepsBySpeaker, collectRetrySteps };
