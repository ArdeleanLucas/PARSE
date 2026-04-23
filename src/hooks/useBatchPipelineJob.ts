import { useState, useRef, useCallback, useEffect, type SetStateAction } from "react";
import { startCompute, pollCompute } from "../api/client";
import type { PipelineRunResult } from "../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export interface BatchRunRequest {
  speakers: string[];
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
  language?: string;
}

export interface BatchSpeakerOutcome {
  speaker: string;
  status: "pending" | "running" | "complete" | "error";
  /** Whole-speaker error (e.g. network failure before the pipeline job even started).
   *  Step-level errors live in `result.results[step].error` instead. */
  error: string | null;
  result: PipelineRunResult | null;
}

export interface BatchState {
  status: "idle" | "running" | "complete";
  totalSpeakers: number;
  completedSpeakers: number;
  currentSpeakerIndex: number | null;
  currentSpeaker: string | null;
  currentSubJobId: string | null;
  currentProgress: number;
  currentMessage: string | null;
  outcomes: BatchSpeakerOutcome[];
}

export interface UseBatchPipelineJobResult {
  state: BatchState;
  run: (request: BatchRunRequest) => Promise<void>;
  reset: () => void;
}

const IDLE_STATE: BatchState = {
  status: "idle",
  totalSpeakers: 0,
  completedSpeakers: 0,
  currentSpeakerIndex: null,
  currentSpeaker: null,
  currentSubJobId: null,
  currentProgress: 0,
  currentMessage: null,
  outcomes: [],
};

const POLL_INTERVAL_MS = 1500;

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  return fallback;
}

function normalizeProgress(progress: number): number {
  if (!Number.isFinite(progress) || progress < 0) {
    return 0;
  }
  if (progress > 1) {
    return Math.min(1, progress / 100);
  }
  return Math.min(1, progress);
}

function isCompleteStatus(status: string): boolean {
  return (
    status === "complete" ||
    status === "done" ||
    status === "success" ||
    status === "succeeded"
  );
}

function isErrorStatus(status: string): boolean {
  return status === "error" || status === "failed" || status === "failure";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function useBatchPipelineJob(): UseBatchPipelineJobResult {
  const [state, setState] = useState<BatchState>(IDLE_STATE);
  const stateRef = useRef<BatchState>(IDLE_STATE);
  const mountedRef = useRef(true);
  const runningRef = useRef(false);
  const activeRunIdRef = useRef(0);

  const setStateIfMounted = useCallback(
    (nextState: SetStateAction<BatchState>) => {
      if (!mountedRef.current) {
        return;
      }
      setState((prev) => {
        const resolved =
          typeof nextState === "function"
            ? (nextState as (s: BatchState) => BatchState)(prev)
            : nextState;
        stateRef.current = resolved;
        return resolved;
      });
    },
    [],
  );

  const reset = useCallback(() => {
    if (runningRef.current) {
      // No-op: mid-batch resets risk leaving dangling polls + confused state.
      return;
    }
    activeRunIdRef.current += 1;
    stateRef.current = IDLE_STATE;
    setStateIfMounted(IDLE_STATE);
  }, [setStateIfMounted]);

  const run = useCallback(
    async (request: BatchRunRequest): Promise<void> => {
      if (runningRef.current) {
        return;
      }
      runningRef.current = true;
      activeRunIdRef.current += 1;
      const runId = activeRunIdRef.current;

      const speakers = request.speakers.slice();
      const outcomes: BatchSpeakerOutcome[] = speakers.map((speaker) => ({
        speaker,
        status: "pending",
        error: null,
        result: null,
      }));

      const initial: BatchState = {
        status: "running",
        totalSpeakers: speakers.length,
        completedSpeakers: 0,
        currentSpeakerIndex: null,
        currentSpeaker: null,
        currentSubJobId: null,
        currentProgress: 0,
        currentMessage: null,
        outcomes,
      };
      stateRef.current = initial;
      setStateIfMounted(initial);

      const isActive = () =>
        mountedRef.current && activeRunIdRef.current === runId;

      try {
        for (let i = 0; i < speakers.length; i += 1) {
          if (!isActive()) return;

          const speaker = speakers[i];

          // Mark this speaker as running.
          setStateIfMounted((prev) => {
            const nextOutcomes = prev.outcomes.slice();
            nextOutcomes[i] = { ...nextOutcomes[i], status: "running" };
            return {
              ...prev,
              currentSpeakerIndex: i,
              currentSpeaker: speaker,
              currentSubJobId: null,
              currentProgress: 0,
              currentMessage: null,
              outcomes: nextOutcomes,
            };
          });

          // Start the per-speaker pipeline job.
          let jobId = "";
          try {
            const body: Record<string, unknown> = {
              speaker,
              steps: request.steps,
              overwrites: request.overwrites,
            };
            if (request.language) {
              body.language = request.language;
            }
            const job = await startCompute("full_pipeline", body);
            if (!isActive()) return;
            jobId = String(job.job_id || "").trim();
            if (!jobId) {
              throw new Error("Missing pipeline job id");
            }
          } catch (error) {
            if (!isActive()) return;
            const message = toErrorMessage(error, "Pipeline start failed");
            setStateIfMounted((prev) => {
              const nextOutcomes = prev.outcomes.slice();
              nextOutcomes[i] = {
                ...nextOutcomes[i],
                status: "error",
                error: message,
              };
              return {
                ...prev,
                completedSpeakers: prev.completedSpeakers + 1,
                currentSubJobId: null,
                currentProgress: 0,
                currentMessage: null,
                outcomes: nextOutcomes,
              };
            });
            continue;
          }

          setStateIfMounted((prev) => ({ ...prev, currentSubJobId: jobId }));

          // Poll loop — lives for one speaker.
          let pollErrored = false;
          let pollResult: PipelineRunResult | null = null;
          let pollErrorMessage: string | null = null;

          while (isActive()) {
            let poll;
            try {
              poll = await pollCompute("full_pipeline", jobId);
            } catch (error) {
              if (!isActive()) return;
              pollErrored = true;
              pollErrorMessage = toErrorMessage(error, "Pipeline poll failed");
              break;
            }
            if (!isActive()) return;

            const progress = normalizeProgress(Number(poll.progress ?? 0));
            const status = String(poll.status || "running").toLowerCase();
            const message =
              typeof poll.message === "string" && poll.message ? poll.message : null;

            setStateIfMounted((prev) => ({
              ...prev,
              currentProgress: progress,
              currentMessage: message,
            }));

            if (isCompleteStatus(status)) {
              // `pollCompute` returns ComputeStatus; the full PipelineRunResult
              // lives under `result` on the same payload (shape documented in
              // api/client.ts). Pull it off the raw response if present.
              const raw = poll as unknown as { result?: PipelineRunResult };
              pollResult = raw.result ?? null;
              break;
            }
            if (isErrorStatus(status)) {
              pollErrored = true;
              pollErrorMessage = poll.error ?? poll.message ?? "Pipeline failed";
              break;
            }

            await delay(POLL_INTERVAL_MS);
            if (!isActive()) return;
          }

          if (!isActive()) return;

          setStateIfMounted((prev) => {
            const nextOutcomes = prev.outcomes.slice();
            if (pollErrored) {
              nextOutcomes[i] = {
                ...nextOutcomes[i],
                status: "error",
                error: pollErrorMessage,
              };
            } else {
              nextOutcomes[i] = {
                ...nextOutcomes[i],
                status: "complete",
                result: pollResult,
              };
            }
            return {
              ...prev,
              completedSpeakers: prev.completedSpeakers + 1,
              currentSubJobId: null,
              currentProgress: 0,
              currentMessage: null,
              outcomes: nextOutcomes,
            };
          });
        }

        if (!isActive()) return;

        setStateIfMounted((prev) => ({
          ...prev,
          status: "complete",
          currentSpeakerIndex: null,
          currentSpeaker: null,
          currentSubJobId: null,
          currentProgress: 0,
          currentMessage: null,
        }));
      } finally {
        if (activeRunIdRef.current === runId) {
          runningRef.current = false;
        }
      }
    },
    [setStateIfMounted],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      runningRef.current = false;
      activeRunIdRef.current += 1;
    };
  }, []);

  return { state, run, reset };
}
