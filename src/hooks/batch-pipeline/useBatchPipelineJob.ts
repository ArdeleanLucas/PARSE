import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";

import { cancelComputeJob } from "../../api/client";
import { startBatchSpeakerJob } from "./useBatchJobStart";
import { pollBatchSpeakerJob } from "./useBatchJobPoll";
import { createRunningState, markPendingSpeakersCancelled, resolveStepsForSpeaker } from "./useBatchJobResults";
import { toErrorMessage } from "./useBatchJobErrors";
import type { BatchRunRequest, BatchState, UseBatchPipelineJobResult } from "./types";
import { IDLE_STATE } from "./types";

export function useBatchPipelineJob(): UseBatchPipelineJobResult {
  const [state, setState] = useState<BatchState>(IDLE_STATE);
  const stateRef = useRef(IDLE_STATE);
  const mountedRef = useRef(true);
  const runningRef = useRef(false);
  const activeRunIdRef = useRef(0);
  const cancelRequestedRef = useRef(false);

  const setStateIfMounted = useCallback((nextState: SetStateAction<BatchState>) => {
    if (!mountedRef.current) return;
    setState((prev) => {
      const resolved = typeof nextState === "function" ? (nextState as (s: BatchState) => BatchState)(prev) : nextState;
      stateRef.current = resolved;
      return resolved;
    });
  }, []);

  const reset = useCallback(() => {
    if (runningRef.current) return;
    activeRunIdRef.current += 1;
    cancelRequestedRef.current = false;
    stateRef.current = IDLE_STATE;
    setStateIfMounted(IDLE_STATE);
  }, [setStateIfMounted]);

  const cancel = useCallback(() => {
    if (!runningRef.current) return;
    const activeJobId = stateRef.current.currentSubJobId;
    cancelRequestedRef.current = true;
    setStateIfMounted((prev) => ({ ...prev, status: "cancelling" }));
    if (activeJobId) {
      void cancelComputeJob(activeJobId).catch(() => undefined);
    }
  }, [setStateIfMounted]);

  const run = useCallback(async (request: BatchRunRequest): Promise<void> => {
    if (runningRef.current) return;
    runningRef.current = true;
    cancelRequestedRef.current = false;
    activeRunIdRef.current += 1;
    const runId = activeRunIdRef.current;
    const speakers = request.speakers.slice();
    const isActive = () => mountedRef.current && activeRunIdRef.current === runId;

    stateRef.current = createRunningState(speakers);
    setStateIfMounted(stateRef.current);

    try {
      for (let i = 0; i < speakers.length; i += 1) {
        if (!isActive()) return;
        const speaker = speakers[i];
        if (cancelRequestedRef.current) {
          setStateIfMounted((prev) => ({ ...prev, outcomes: markPendingSpeakersCancelled(prev.outcomes, i) }));
          break;
        }
        setStateIfMounted((prev) => ({
          ...prev,
          currentSpeakerIndex: i,
          currentSpeaker: speaker,
          currentSubJobId: null,
          currentProgress: 0,
          currentMessage: null,
          outcomes: prev.outcomes.map((outcome, index) => index === i ? { ...outcome, status: "running" } : outcome),
        }));

        const stepsForSpeaker = resolveStepsForSpeaker(request, speaker);
        if (stepsForSpeaker.length === 0) {
          setStateIfMounted((prev) => ({
            ...prev,
            completedSpeakers: prev.completedSpeakers + 1,
            currentSpeakerIndex: null,
            currentSpeaker: null,
            currentSubJobId: null,
            currentProgress: 0,
            currentMessage: null,
            outcomes: prev.outcomes.map((outcome, index) => index === i ? { ...outcome, status: "cancelled" } : outcome),
          }));
          continue;
        }

        let jobId = "";
        try {
          jobId = await startBatchSpeakerJob(request, speaker, stepsForSpeaker);
          if (!isActive()) return;
        } catch (error) {
          if (!isActive()) return;
          const message = toErrorMessage(error, "Pipeline start failed");
          setStateIfMounted((prev) => ({
            ...prev,
            completedSpeakers: prev.completedSpeakers + 1,
            currentSubJobId: null,
            currentProgress: 0,
            currentMessage: null,
            outcomes: prev.outcomes.map((outcome, index) => index === i ? { ...outcome, status: "error", error: message, errorPhase: "start" } : outcome),
          }));
          continue;
        }

        setStateIfMounted((prev) => ({
          ...prev,
          currentSubJobId: jobId,
          outcomes: prev.outcomes.map((outcome, index) => index === i ? { ...outcome, jobId, errorPhase: undefined } : outcome),
        }));

        const { pollErrored, pollResult, pollErrorMessage, pollCancelled } = await pollBatchSpeakerJob(jobId, isActive, (progress, message) => {
          setStateIfMounted((prev) => ({ ...prev, currentProgress: progress, currentMessage: message }));
        }, () => cancelRequestedRef.current);
        if (!isActive()) return;

        if (pollCancelled) {
          setStateIfMounted((prev) => {
            const outcomes = markPendingSpeakersCancelled(prev.outcomes, i + 1).map((outcome, index) => index === i
              ? { ...outcome, status: "cancelled" as const, jobId }
              : outcome);
            return {
              ...prev,
              completedSpeakers: prev.completedSpeakers + 1,
              currentSubJobId: null,
              currentProgress: 0,
              currentMessage: null,
              outcomes,
            };
          });
          break;
        }

        setStateIfMounted((prev) => ({
          ...prev,
          completedSpeakers: prev.completedSpeakers + 1,
          currentSubJobId: null,
          currentProgress: 0,
          currentMessage: null,
          outcomes: prev.outcomes.map((outcome, index) => index !== i ? outcome : pollErrored
            ? { ...outcome, status: "error", error: pollErrorMessage, errorPhase: "poll", jobId, result: pollResult }
            : { ...outcome, status: "complete", result: pollResult }),
        }));
      }

      if (!isActive()) return;
      const wasCancelled = cancelRequestedRef.current;
      setStateIfMounted((prev) => ({
        ...prev,
        status: "complete",
        cancelled: wasCancelled,
        currentSpeakerIndex: null,
        currentSpeaker: null,
        currentSubJobId: null,
        currentProgress: 0,
        currentMessage: null,
      }));
    } finally {
      if (activeRunIdRef.current === runId) {
        runningRef.current = false;
        cancelRequestedRef.current = false;
      }
    }
  }, [setStateIfMounted]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      runningRef.current = false;
      activeRunIdRef.current += 1;
    };
  }, []);

  return { state, run, cancel, reset };
}
