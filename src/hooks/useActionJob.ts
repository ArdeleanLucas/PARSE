import { useState, useRef, useCallback, useEffect } from "react";

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

export function useActionJob(config: ActionJobConfig): ActionJobHandle {
  const [state, setState] = useState<ActionJobState>(IDLE_STATE);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);
  const jobIdRef = useRef<string | null>(null);
  const dismissTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (dismissTimeoutRef.current !== null) {
      clearTimeout(dismissTimeoutRef.current);
      dismissTimeoutRef.current = null;
    }
    inFlightRef.current = false;
    jobIdRef.current = null;
  }, []);

  const reset = useCallback(() => {
    stopPolling();
    setState(IDLE_STATE);
  }, [stopPolling]);

  const pollOnce = useCallback(async () => {
    if (inFlightRef.current || !jobIdRef.current) {
      return;
    }

    inFlightRef.current = true;
    try {
      const poll = await config.poll(jobIdRef.current);
      const progress = normalizeProgress(Number(poll.progress ?? 0));
      const status = String(poll.status || "running").toLowerCase();

      if (status === "complete" || status === "done") {
        stopPolling();
        await config.onComplete?.();
        setState({
          status: "complete",
          progress: 1,
          error: null,
          label: config.label,
        });

        if (config.autoDismissMs !== 0) {
          dismissTimeoutRef.current = setTimeout(() => {
            setState(IDLE_STATE);
            dismissTimeoutRef.current = null;
          }, config.autoDismissMs ?? 3000);
        }
        return;
      }

      if (status === "error" || status === "failed") {
        stopPolling();
        setState({
          status: "error",
          progress,
          error: poll.message ?? poll.error ?? "Job failed",
          label: config.label,
        });
        return;
      }

      setState((prev) => ({
        ...prev,
        status: "running",
        progress,
      }));
    } catch (error) {
      stopPolling();
      setState({
        status: "error",
        progress: 0,
        error: toErrorMessage(error, "Job polling failed"),
        label: config.label,
      });
    } finally {
      inFlightRef.current = false;
    }
  }, [config, stopPolling]);

  const run = useCallback(async (): Promise<void> => {
    if (state.status === "running") {
      return;
    }

    stopPolling();
    setState({ status: "running", progress: 0, error: null, label: config.label });

    try {
      const job = await config.start();
      const resolvedJobId = String(job.job_id || "").trim();
      if (!resolvedJobId) {
        throw new Error("Missing action job id");
      }

      jobIdRef.current = resolvedJobId;
      intervalRef.current = setInterval(() => {
        void pollOnce();
      }, config.pollIntervalMs ?? 1000);
    } catch (error) {
      stopPolling();
      setState({
        status: "error",
        progress: 0,
        error: toErrorMessage(error, "Job start failed"),
        label: config.label,
      });
    }
  }, [config.label, config.pollIntervalMs, config.start, pollOnce, state.status, stopPolling]);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  return { state, run, reset };
}
