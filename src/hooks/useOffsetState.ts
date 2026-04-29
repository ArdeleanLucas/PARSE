import { useCallback, useEffect, useMemo, useState } from 'react';
import type { OffsetDetectResult, OffsetPair } from '../api/client';
import { OffsetJobError } from '../api/client';

export interface OffsetWorkflowConcept {
  id: number;
  key: string;
  name: string;
}

export interface ManualAnchor {
  conceptKey: string;
  conceptName: string;
  csvTimeSec: number;
  audioTimeSec: number;
  capturedAt: number;
}

export interface ManualConsensus {
  median: number;
  mad: number;
  offsets: number[];
}

export type OffsetState =
  | { phase: 'idle' }
  | { phase: 'detecting'; jobId: string | null; progress: number; progressMessage?: string; origin: 'auto' | 'manual' }
  | { phase: 'detected'; result: OffsetDetectResult }
  | { phase: 'manual' }
  | { phase: 'applying'; result: OffsetDetectResult }
  | { phase: 'applied'; result: OffsetDetectResult; shifted: number; shiftedConcepts: number; protected: number }
  | { phase: 'error'; message: string; traceback?: string; jobId?: string };

interface UseOffsetStateArgs {
  activeActionSpeaker: string | null;
  selectedConcept: OffsetWorkflowConcept | null;
  protectedLexemeCount: number;
  getCurrentTime: () => number;
  lookupConceptInterval: (speaker: string, concept: OffsetWorkflowConcept) => { start: number; end: number } | null;
  markLexemeManuallyAdjusted: (speaker: string, start: number, end: number) => void;
  detectTimestampOffset: (speaker: string) => Promise<{ jobId?: string; job_id?: string }>;
  detectTimestampOffsetFromPairs: (speaker: string, pairs: OffsetPair[]) => Promise<{ jobId?: string; job_id?: string }>;
  pollOffsetDetectJob: (
    jobId: string,
    computeType: 'offset_detect' | 'offset_detect_from_pair',
    options?: { onProgress?: (p: { progress: number; message?: string }) => void },
  ) => Promise<OffsetDetectResult>;
  applyTimestampOffset: (speaker: string, offsetSec: number) => Promise<{
    shiftedIntervals?: number;
    shiftedConcepts?: number;
    protectedIntervals?: number;
    protectedLexemes?: number;
    shifted?: number;
    protected?: number;
  }>;
  reloadSpeakerAnnotation: (speaker: string) => Promise<void>;
  onCloseActionsMenu?: () => void;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 0) return 0;
  if (sorted.length % 2 === 1) return sorted[(sorted.length - 1) / 2];
  return (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
}

export function formatPlaybackTime(t: number): string {
  if (!Number.isFinite(t) || t < 0) return '00:00.00';
  const m = Math.floor(t / 60).toString().padStart(2, '0');
  const s = Math.floor(t % 60).toString().padStart(2, '0');
  const ms = Math.floor((t * 100) % 100).toString().padStart(2, '0');
  return `${m}:${s}.${ms}`;
}

function resolveJobId(job: { jobId?: string; job_id?: string }): string | null {
  return job.jobId ?? job.job_id ?? null;
}

export function useOffsetState({
  activeActionSpeaker,
  selectedConcept,
  getCurrentTime,
  lookupConceptInterval,
  markLexemeManuallyAdjusted,
  detectTimestampOffset,
  detectTimestampOffsetFromPairs,
  pollOffsetDetectJob,
  applyTimestampOffset,
  reloadSpeakerAnnotation,
  onCloseActionsMenu,
}: UseOffsetStateArgs) {
  const [offsetState, setOffsetState] = useState<OffsetState>({ phase: 'idle' });
  const [jobLogsOpen, setJobLogsOpen] = useState<string | null>(null);
  const [manualAnchors, setManualAnchors] = useState<ManualAnchor[]>([]);
  const [manualBusy, setManualBusy] = useState(false);
  const [captureToast, setCaptureToast] = useState<string | null>(null);
  const [lastProgressMessage, setLastProgressMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!captureToast) return;
    const handle = window.setTimeout(() => setCaptureToast(null), 2200);
    return () => window.clearTimeout(handle);
  }, [captureToast]);

  const manualConsensus = useMemo<ManualConsensus | null>(() => {
    if (!manualAnchors.length) return null;
    const offsets = manualAnchors.map((anchor) => anchor.audioTimeSec - anchor.csvTimeSec);
    const medianOffset = median(offsets);
    const deviations = offsets.map((offset) => Math.abs(offset - medianOffset));
    return {
      median: medianOffset,
      mad: deviations.length <= 1 ? 0 : median(deviations),
      offsets,
    };
  }, [manualAnchors]);

  const captureCurrentAnchor = useCallback((): { ok: boolean; message: string } => {
    if (!activeActionSpeaker) {
      return { ok: false, message: 'Select a speaker first.' };
    }
    if (!selectedConcept) {
      return { ok: false, message: 'Select a lexeme in the sidebar first.' };
    }
    const interval = lookupConceptInterval(activeActionSpeaker, selectedConcept);
    if (interval === null) {
      return {
        ok: false,
        message: `No annotation interval for "${selectedConcept.name}" — open the lexeme in Annotate first.`,
      };
    }
    const audio = getCurrentTime();
    if (audio <= 0) {
      return {
        ok: false,
        message: 'Scrub the waveform to where the lexeme actually is, then capture again.',
      };
    }
    setManualAnchors((prev) => {
      const filtered = prev.filter((anchor) => anchor.conceptKey !== selectedConcept.key);
      return [
        ...filtered,
        {
          conceptKey: selectedConcept.key,
          conceptName: selectedConcept.name,
          csvTimeSec: interval.start,
          audioTimeSec: audio,
          capturedAt: Date.now(),
        },
      ];
    });
    markLexemeManuallyAdjusted(activeActionSpeaker, interval.start, interval.end);
    const offset = audio - interval.start;
    const sign = offset >= 0 ? '+' : '';
    return {
      ok: true,
      message: `Anchored ${selectedConcept.name} @ ${formatPlaybackTime(audio)} → ${sign}${offset.toFixed(2)}s offset.`,
    };
  }, [activeActionSpeaker, selectedConcept, lookupConceptInterval, getCurrentTime, markLexemeManuallyAdjusted]);

  const captureAnchorFromBar = useCallback(() => {
    const result = captureCurrentAnchor();
    setCaptureToast(result.message);
  }, [captureCurrentAnchor]);

  const removeManualAnchor = useCallback((conceptKey: string) => {
    setManualAnchors((prev) => prev.filter((anchor) => anchor.conceptKey !== conceptKey));
  }, []);

  const openManualOffset = useCallback(() => {
    onCloseActionsMenu?.();
    setOffsetState({ phase: 'manual' });
  }, [onCloseActionsMenu]);

  const closeOffsetModal = useCallback(() => {
    setOffsetState({ phase: 'idle' });
  }, []);

  const openJobLogs = useCallback((jobId: string) => {
    setJobLogsOpen(jobId);
  }, []);

  const closeJobLogs = useCallback(() => {
    setJobLogsOpen(null);
  }, []);

  const detectOffsetForSpeaker = useCallback(async () => {
    onCloseActionsMenu?.();
    if (!activeActionSpeaker) {
      setOffsetState({ phase: 'error', message: 'Select a speaker first.' });
      return;
    }
    setLastProgressMessage(null);
    setOffsetState({ phase: 'detecting', jobId: null, progress: 0, origin: 'auto' });
    let submittedJobId: string | null = null;
    try {
      const job = await detectTimestampOffset(activeActionSpeaker);
      const jobId = resolveJobId(job);
      if (!jobId) throw new Error('Server did not return a job ID for offset detection');
      submittedJobId = jobId;
      setOffsetState({ phase: 'detecting', jobId, progress: 0, origin: 'auto' });
      const result = await pollOffsetDetectJob(jobId, 'offset_detect', {
        onProgress: ({ progress, message }) => {
          setLastProgressMessage(message ?? null);
          setOffsetState((prev) =>
            prev.phase === 'detecting'
              ? { ...prev, progress, progressMessage: message }
              : prev,
          );
        },
      });
      setOffsetState({ phase: 'detected', result });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const traceback = err instanceof OffsetJobError ? err.traceback : undefined;
      const jobId = err instanceof OffsetJobError ? err.jobId : submittedJobId ?? undefined;
      setOffsetState({ phase: 'error', message, traceback, jobId });
    }
  }, [activeActionSpeaker, detectTimestampOffset, onCloseActionsMenu, pollOffsetDetectJob]);

  const applyDetectedOffset = useCallback(async () => {
    if (offsetState.phase !== 'detected') return;
    const { result } = offsetState;
    setOffsetState({ phase: 'applying', result });
    try {
      const apply = await applyTimestampOffset(result.speaker, result.offsetSec);
      await reloadSpeakerAnnotation(result.speaker);
      setOffsetState({
        phase: 'applied',
        result,
        shifted: apply.shiftedIntervals ?? apply.shifted ?? 0,
        shiftedConcepts: apply.shiftedConcepts ?? apply.shiftedIntervals ?? apply.shifted ?? 0,
        protected: apply.protectedLexemes ?? apply.protected ?? 0,
      });
    } catch (err) {
      setOffsetState({
        phase: 'error',
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, [applyTimestampOffset, offsetState, reloadSpeakerAnnotation]);

  const submitManualOffset = useCallback(async () => {
    if (!activeActionSpeaker) {
      setOffsetState({ phase: 'error', message: 'Select a speaker first.' });
      return;
    }
    if (!manualAnchors.length) {
      setOffsetState({ phase: 'error', message: 'Capture at least one anchor before computing the offset.' });
      return;
    }
    setManualBusy(true);
    setLastProgressMessage(null);
    let submittedJobId: string | null = null;
    try {
      const pairs: OffsetPair[] = manualAnchors.map((anchor) => ({
        audioTimeSec: anchor.audioTimeSec,
        csvTimeSec: anchor.csvTimeSec,
      }));
      const job = await detectTimestampOffsetFromPairs(activeActionSpeaker, pairs);
      const jobId = resolveJobId(job);
      if (!jobId) throw new Error('Server did not return a job ID');
      submittedJobId = jobId;
      setOffsetState({ phase: 'detecting', jobId, progress: 0, origin: 'manual' });
      const result = await pollOffsetDetectJob(jobId, 'offset_detect_from_pair', {
        onProgress: ({ progress, message }) => {
          setLastProgressMessage(message ?? null);
          setOffsetState((prev) =>
            prev.phase === 'detecting'
              ? { ...prev, progress, progressMessage: message }
              : prev,
          );
        },
      });
      setOffsetState({ phase: 'detected', result });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const traceback = err instanceof OffsetJobError ? err.traceback : undefined;
      const jobId = err instanceof OffsetJobError ? err.jobId : submittedJobId ?? undefined;
      setOffsetState({ phase: 'error', message, traceback, jobId });
    } finally {
      setManualBusy(false);
    }
  }, [activeActionSpeaker, detectTimestampOffsetFromPairs, manualAnchors, pollOffsetDetectJob]);

  return {
    offsetState,
    setOffsetState,
    jobLogsOpen,
    openJobLogs,
    closeJobLogs,
    manualAnchors,
    manualBusy,
    captureToast,
    lastProgressMessage,
    manualConsensus,
    openManualOffset,
    closeOffsetModal,
    captureCurrentAnchor,
    captureAnchorFromBar,
    removeManualAnchor,
    detectOffsetForSpeaker,
    applyDetectedOffset,
    submitManualOffset,
  };
}
