import { useState, useRef, useCallback, useEffect, type SetStateAction } from "react";

export interface PollResult {
  status: string;
  progress?: number;
  message?: string;
  error?: string;
}

export interface ActionJobState {
  status: "idle" | "running" | "complete" | "error";
  progress: number;
  error: string | null;
  label: string | null;
  /** ms remaining, projected from elapsed time and current progress. null until the projection is stable. */
  etaMs: number | null;
  /** Latest status message from the backend (e.g. "Loading model", "Transcribing"). null when idle or unknown. */
  message: string | null;
}

const MIN_PROGRESS_FOR_ETA = 0.05
const MIN_ELAPSED_MS_FOR_ETA = 1500

export function projectEtaMs(progress: number, elapsedMs: number): number | null {
  if (!Number.isFinite(progress) || !Number.isFinite(elapsedMs)) return null
  if (progress < MIN_PROGRESS_FOR_ETA) return null
  if (elapsedMs < MIN_ELAPSED_MS_FOR_ETA) return null
  if (progress >= 1) return 0
  const remaining = (elapsedMs / progress) * (1 - progress)
  if (!Number.isFinite(remaining) || remaining < 0) return null
  return Math.round(remaining)
}

export function formatEta(ms: number): string {
  if (ms < 1000) return "<1s"
  const totalSeconds = Math.round(ms / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes < 60) return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

export interface ActionJobConfig {
  start: () => Promise<{ job_id: string }>;
  poll: (jobId: string) => Promise<PollResult>;
  label: string;
  /** Called exactly once when the backend reports a terminal success
   *  status. Receives the poll's opaque ``result`` payload so callers can
   *  inspect what the job actually produced (e.g. CLEF populate returns
   *  ``{filled, total_filled, warning?}``) and surface warnings that
   *  don't warrant an error status but still matter to the user. */
  onComplete?: (result?: unknown) => void | Promise<void>;
  pollIntervalMs?: number;
  autoDismissMs?: number;
}

export interface ActionJobHandle {
  state: ActionJobState;
  run: () => Promise<void>;
  reset: () => void;
  /** Attach to an already-running backend job (e.g. one launched before a
   * page reload) and start polling its status. Skips config.start(). */
  adopt: (jobId: string) => void;
}

const IDLE_STATE: ActionJobState = {
  status: "idle",
  progress: 0,
  error: null,
  label: null,
  etaMs: null,
  message: null,
};

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
  return status === "complete" || status === "done" || status === "success" || status === "succeeded";
}

function isErrorStatus(status: string): boolean {
  return status === "error" || status === "failed" || status === "failure";
}

export function useActionJob(config: ActionJobConfig): ActionJobHandle {
  const [state, setState] = useState<ActionJobState>(IDLE_STATE);
  const stateRef = useRef<ActionJobState>(IDLE_STATE);
  const mountedRef = useRef(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollInFlightRef = useRef(false);
  const startInFlightRef = useRef(false);
  const jobIdRef = useRef<string | null>(null);
  const dismissTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRunIdRef = useRef(0);
  const startedAtRef = useRef<number | null>(null);

  const setStateIfMounted = useCallback((nextState: SetStateAction<ActionJobState>) => {
    if (!mountedRef.current) {
      return;
    }

    setState((previousState) => {
      const resolvedState = typeof nextState === "function"
        ? nextState(previousState)
        : nextState;
      stateRef.current = resolvedState;
      return resolvedState;
    });
  }, []);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (dismissTimeoutRef.current !== null) {
      clearTimeout(dismissTimeoutRef.current);
      dismissTimeoutRef.current = null;
    }
    pollInFlightRef.current = false;
    jobIdRef.current = null;
  }, []);

  const reset = useCallback(() => {
    activeRunIdRef.current += 1;
    startInFlightRef.current = false;
    stopPolling();
    stateRef.current = IDLE_STATE;
    setStateIfMounted(IDLE_STATE);
  }, [setStateIfMounted, stopPolling]);

  const pollOnce = useCallback(async (runId: number) => {
    if (pollInFlightRef.current || !jobIdRef.current || activeRunIdRef.current !== runId) {
      return;
    }

    pollInFlightRef.current = true;
    try {
      const poll = await config.poll(jobIdRef.current);
      if (activeRunIdRef.current !== runId) {
        return;
      }

      const progress = normalizeProgress(Number(poll.progress ?? 0));
      const status = String(poll.status || "running").toLowerCase();

      if (isCompleteStatus(status)) {
        stopPolling();
        try {
          // Pass the backend's opaque result through so callers can
          // branch on it -- e.g. CLEF populate flags "0 forms" as a
          // warning even though the job status itself is "complete".
          await config.onComplete?.((poll as { result?: unknown }).result);
        } catch (error) {
          if (activeRunIdRef.current !== runId) {
            return;
          }
          setStateIfMounted({
            status: "error",
            progress,
            error: toErrorMessage(error, `${config.label} follow-up failed`),
            label: config.label,
            etaMs: null,
            message: null,
          });
          return;
        }

        if (activeRunIdRef.current !== runId) {
          return;
        }

        setStateIfMounted({
          status: "complete",
          progress: 1,
          error: null,
          label: config.label,
          etaMs: 0,
          message: null,
        });

        if (config.autoDismissMs !== 0) {
          dismissTimeoutRef.current = setTimeout(() => {
            stateRef.current = IDLE_STATE;
            setStateIfMounted(IDLE_STATE);
            dismissTimeoutRef.current = null;
          }, config.autoDismissMs ?? 3000);
        }
        return;
      }

      if (isErrorStatus(status)) {
        stopPolling();
        setStateIfMounted({
          status: "error",
          progress,
          message: null,
          // Surface the actual exception (`poll.error`) first — `poll.message`
          // is the last in-progress status line ("Loading model", "Initializing
          // STT provider") and was masking the real failures.
          error: poll.error ?? poll.message ?? "Job failed",
          label: config.label,
          etaMs: null,
        });
        return;
      }

      const elapsed = startedAtRef.current === null ? 0 : Date.now() - startedAtRef.current;
      const etaMs = projectEtaMs(progress, elapsed);
      const message = poll.message != null ? String(poll.message) : null;
      setStateIfMounted((prev) => ({
        ...prev,
        status: "running",
        progress,
        etaMs,
        message,
      }));
    } catch (error) {
      if (activeRunIdRef.current !== runId) {
        return;
      }
      stopPolling();
      setStateIfMounted({
        status: "error",
        progress: 0,
        error: toErrorMessage(error, "Job polling failed"),
        label: config.label,
        etaMs: null,
        message: null,
      });
    } finally {
      pollInFlightRef.current = false;
    }
  }, [config, setStateIfMounted, stopPolling]);

  const adopt = useCallback((jobId: string): void => {
    const trimmed = String(jobId || "").trim();
    if (!trimmed || stateRef.current.status === "running") {
      return;
    }

    activeRunIdRef.current += 1;
    const runId = activeRunIdRef.current;

    stopPolling();
    startedAtRef.current = Date.now();
    jobIdRef.current = trimmed;
    setStateIfMounted({
      status: "running",
      progress: 0,
      error: null,
      label: config.label,
      etaMs: null,
      message: null,
    });

    // Fire an immediate poll so the bar picks up real progress without
    // waiting a full interval.
    void pollOnce(runId);
    intervalRef.current = setInterval(() => {
      void pollOnce(runId);
    }, config.pollIntervalMs ?? 1000);
  }, [config.label, config.pollIntervalMs, pollOnce, setStateIfMounted, stopPolling]);

  const run = useCallback(async (): Promise<void> => {
    if (startInFlightRef.current || stateRef.current.status === "running") {
      return;
    }

    activeRunIdRef.current += 1;
    const runId = activeRunIdRef.current;

    startInFlightRef.current = true;
    stopPolling();
    startedAtRef.current = Date.now();
    setStateIfMounted({ status: "running", progress: 0, error: null, label: config.label, etaMs: null, message: null });

    try {
      const job = await config.start();
      if (activeRunIdRef.current !== runId) {
        return;
      }

      const resolvedJobId = String(job.job_id || "").trim();
      if (!resolvedJobId) {
        throw new Error("Missing action job id");
      }

      jobIdRef.current = resolvedJobId;
      intervalRef.current = setInterval(() => {
        void pollOnce(runId);
      }, config.pollIntervalMs ?? 1000);
    } catch (error) {
      if (activeRunIdRef.current !== runId) {
        return;
      }
      stopPolling();
      setStateIfMounted({
        status: "error",
        progress: 0,
        error: toErrorMessage(error, "Job start failed"),
        label: config.label,
        etaMs: null,
        message: null,
      });
    } finally {
      if (activeRunIdRef.current === runId) {
        startInFlightRef.current = false;
      }
    }
  }, [config.label, config.pollIntervalMs, config.start, pollOnce, setStateIfMounted, stopPolling]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      startInFlightRef.current = false;
      activeRunIdRef.current += 1;
      stopPolling();
    };
  }, [stopPolling]);

  return { state, run, reset, adopt };
}
