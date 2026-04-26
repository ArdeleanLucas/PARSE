import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TranscriptionRunConfirm } from '../components/shared/TranscriptionRunModal';
import { useBatchPipelineJob, type BatchSpeakerOutcome, type PipelineStepId, type UseBatchPipelineJobResult } from './useBatchPipelineJob';

const PIPELINE_STEP_ORDER: PipelineStepId[] = ['normalize', 'stt', 'ortho', 'ipa'];

export interface UseParseUIPipelineArgs {
  closeRunModal: () => void;
  openBatchReport: () => void;
  closeBatchReport: () => void;
  isBatchReportOpen: boolean;
  getLanguage: () => string | undefined;
  reloadSpeakerAnnotation: (speakerId: string) => Promise<void>;
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

export function useParseUIPipeline({
  closeRunModal,
  openBatchReport,
  closeBatchReport,
  isBatchReportOpen,
  getLanguage,
  reloadSpeakerAnnotation,
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
            await reloadSpeakerAnnotation(outcome.speaker);
          }
        }
        await loadEnrichments();
      })();
    }
    previousBatchStatusRef.current = batch.state.status;
  }, [batch.state.status, batch.state.outcomes, loadEnrichments, openBatchReport, reloadSpeakerAnnotation, reloadStt]);

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
