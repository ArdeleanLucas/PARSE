import { useState, useRef, useCallback, useEffect, type SetStateAction } from "react";
import { startCompute, pollCompute } from "../api/client";
import type { PipelineRunResult } from "../api/client";

export type PipelineStepId = "normalize" | "stt" | "ortho" | "ipa";

export interface BatchRunRequest {
  speakers: string[];
  steps: PipelineStepId[];
  overwrites: Partial<Record<PipelineStepId, boolean>>;
  language?: string;
  /** Optional per-speaker step overrides. When a speaker key is present here,
   *  the batch runs those steps for that speaker instead of the global
   *  `steps` list. Used by "Rerun failed" so each speaker only retries the
   *  steps that actually failed last time — prevents re-running (and
   *  overwriting) steps that succeeded for that speaker. */
  stepsBySpeaker?: Partial<Record<string, PipelineStepId[]>>;
}

export interface BatchSpeakerOutcome {
  speaker: string;
  /** "cancelled" means the user cancelled the batch before this speaker ran.
   *  The speaker's pipeline never started server-side. */
  status: "pending" | "running" | "complete" | "error" | "cancelled";
  /** Whole-speaker error (e.g. network failure before the pipeline job even started).
   *  Step-level errors live in `result.results[step].error` instead. */
  error: string | null;
  result: PipelineRunResult | null;
}

export interface BatchState {
  /** "cancelling" is a brief transitional state between cancel() and the
   *  current speaker's poll loop exiting. "complete" means the batch
   *  finished — either organically or because it was cancelled. Use
   *  `cancelled` to tell the two complete variants apart. */
  status: "idle" | "running" | "cancelling" | "complete";
  cancelled: boolean;
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
  /** Request that the batch stop after the currently-running speaker's
   *  pipeline finishes. The current speaker's server-side work continues
   *  to completion (there is no server cancel endpoint — the GPU cycles
   *  are already spent). Remaining unstarted speakers are marked
   *  "cancelled" in outcomes. Safe to call any time; no-op when idle. */
  cancel: () => void;
  reset: () => void;
}

const IDLE_STATE: BatchState = {
  status: "idle",
  cancelled: false,
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
  // Set by `cancel()`; checked between speakers to stop launching new
  // pipeline jobs. The current speaker's in-flight poll continues until
  // the server-side job completes (there is no server-side abort).
  const cancelRequestedRef = useRef(false);

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
    cancelRequestedRef.current = false;
    stateRef.current = IDLE_STATE;
    setStateIfMounted(IDLE_STATE);
  }, [setStateIfMounted]);

  const cancel = useCallback(() => {
    if (!runningRef.current) return;
    cancelRequestedRef.current = true;
    setStateIfMounted((prev) => ({ ...prev, status: "cancelling" }));
  }, [setStateIfMounted]);

  const run = useCallback(
    async (request: BatchRunRequest): Promise<void> => {
      if (runningRef.current) {
        return;
      }
      runningRef.current = true;
      cancelRequestedRef.current = false;
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
        cancelled: false,
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

          // Honor cancel: mark this and all subsequent speakers as
          // "cancelled" and exit the loop. No new server-side jobs.
          if (cancelRequestedRef.current) {
            setStateIfMounted((prev) => {
              const nextOutcomes = prev.outcomes.slice();
              for (let j = i; j < nextOutcomes.length; j += 1) {
                if (nextOutcomes[j].status === "pending") {
                  nextOutcomes[j] = { ...nextOutcomes[j], status: "cancelled" };
                }
              }
              return { ...prev, outcomes: nextOutcomes };
            });
            break;
          }

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

          // Resolve the steps for THIS speaker — either a per-speaker
          // override (e.g. rerun-failed with speaker-specific failed
          // steps) or the batch-wide default.
          const stepsForSpeaker =
            request.stepsBySpeaker?.[speaker] ?? request.steps;

          // If the per-speaker override is empty, there's nothing to do
          // for this speaker — mark it cancelled (not errored, since the
          // caller chose to skip) and move on.
          if (stepsForSpeaker.length === 0) {
            setStateIfMounted((prev) => {
              const nextOutcomes = prev.outcomes.slice();
              nextOutcomes[i] = { ...nextOutcomes[i], status: "cancelled" };
              return {
                ...prev,
                completedSpeakers: prev.completedSpeakers + 1,
                currentSpeakerIndex: null,
                currentSpeaker: null,
                currentSubJobId: null,
                currentProgress: 0,
                currentMessage: null,
                outcomes: nextOutcomes,
              };
            });
            continue;
          }

          // Start the per-speaker pipeline job.
          let jobId = "";
          try {
            const body: Record<string, unknown> = {
              speaker,
              steps: stepsForSpeaker,
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

            // Regardless of terminal status (complete OR error), the backend
            // may have populated ``result`` with step-level details — e.g.
            // a full_pipeline that completed STT then errored on IPA returns
            // a ``results`` dict with per-step status/error/traceback even
            // when the job-level status is "error". Previously we dropped
            // that on the error branch, leaving the user with only the
            // top-line "Pipeline failed" message and no way to see which
            // step actually failed or why. Capture it on both paths.
            const raw = poll as unknown as { result?: PipelineRunResult };

            if (isCompleteStatus(status)) {
              pollResult = raw.result ?? null;
              break;
            }
            if (isErrorStatus(status)) {
              pollErrored = true;
              pollErrorMessage = poll.error ?? poll.message ?? "Pipeline failed";
              // Keep any partial per-step results so the modal can still
              // render step-by-step status. A job-level error does NOT
              // invalidate the steps that completed before it.
              pollResult = raw.result ?? null;
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
                // Partial per-step data where present — see the comment in
                // the poll loop for why we forward this on the error path.
                result: pollResult,
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

  return { state, run, cancel, reset };
}
