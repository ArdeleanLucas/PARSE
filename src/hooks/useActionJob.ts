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
}

export interface ActionJobConfig {
  start: () => Promise<{ job_id: string }>;
  poll: (jobId: string) => Promise<PollResult>;
  label: string;
  onComplete?: () => void | Promise<void>;
  pollIntervalMs?: number;
  autoDismissMs?: number;
}

export interface ActionJobHandle {
  state: ActionJobState;
  run: () => Promise<void>;
  reset: () => void;
}

const IDLE_STATE: ActionJobState = {
  status: "idle",
  progress: 0,
  error: null,
  label: null,
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
          await config.onComplete?.();
        } catch (error) {
          if (activeRunIdRef.current !== runId) {
            return;
          }
          setStateIfMounted({
            status: "error",
            progress,
            error: toErrorMessage(error, `${config.label} follow-up failed`),
            label: config.label,
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
          error: poll.message ?? poll.error ?? "Job failed",
          label: config.label,
        });
        return;
      }

      setStateIfMounted((prev) => ({
        ...prev,
        status: "running",
        progress,
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
      });
    } finally {
      pollInFlightRef.current = false;
    }
  }, [config, setStateIfMounted, stopPolling]);

  const run = useCallback(async (): Promise<void> => {
    if (startInFlightRef.current || stateRef.current.status === "running") {
      return;
    }

    activeRunIdRef.current += 1;
    const runId = activeRunIdRef.current;

    startInFlightRef.current = true;
    stopPolling();
    setStateIfMounted({ status: "running", progress: 0, error: null, label: config.label });

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

  return { state, run, reset };
}
