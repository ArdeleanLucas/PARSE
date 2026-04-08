import { useState, useRef, useCallback, useEffect } from "react";
import { startCompute, pollCompute } from "../api/client";
import { useEnrichmentStore } from "../stores/enrichmentStore";

export interface ComputeJobState {
  status: "idle" | "running" | "complete" | "error";
  progress: number; // 0.0 – 1.0
  error: string | null;
}

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

export function useComputeJob(computeType: string) {
  const [state, setState] = useState<ComputeJobState>({
    status: "idle",
    progress: 0,
    error: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);
  const jobIdRef = useRef<string | null>(null);
  const loadEnrichments = useEnrichmentStore((store) => store.load);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    inFlightRef.current = false;
    jobIdRef.current = null;
  }, []);

  const pollOnce = useCallback(async () => {
    if (inFlightRef.current || !jobIdRef.current) {
      return;
    }

    inFlightRef.current = true;
    try {
      const poll = await pollCompute(computeType, jobIdRef.current);
      const progress = normalizeProgress(Number(poll.progress ?? 0));
      const status = String(poll.status || "running").toLowerCase();

      if (status === "complete" || status === "done") {
        stopPolling();
        await loadEnrichments();
        setState({ status: "complete", progress: 1, error: null });
        return;
      }

      if (status === "error" || status === "failed") {
        stopPolling();
        setState({
          status: "error",
          progress,
          error: poll.message ?? poll.error ?? "Compute failed",
        });
        return;
      }

      setState((prev) => ({ ...prev, status: "running", progress }));
    } catch (error) {
      stopPolling();
      setState({
        status: "error",
        progress: 0,
        error: toErrorMessage(error, "Compute polling failed"),
      });
    } finally {
      inFlightRef.current = false;
    }
  }, [computeType, loadEnrichments, stopPolling]);

  const start = useCallback(async (): Promise<void> => {
    stopPolling();
    setState({ status: "running", progress: 0, error: null });

    try {
      const job = await startCompute(computeType);
      const resolvedJobId = String(job.job_id || job.jobId || "").trim();
      if (!resolvedJobId) {
        throw new Error("Missing compute job id");
      }

      jobIdRef.current = resolvedJobId;
      intervalRef.current = setInterval(() => {
        void pollOnce();
      }, 1000);
    } catch (error) {
      stopPolling();
      setState({
        status: "error",
        progress: 0,
        error: toErrorMessage(error, "Compute start failed"),
      });
    }
  }, [computeType, pollOnce, stopPolling]);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  return { start, state };
}
