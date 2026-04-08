// useComputeJob — phonetic compute job lifecycle for one speaker.
// Used by EnrichmentsPanel [Run Compute] button.
import { useState, useRef, useCallback, useEffect } from "react";
import { startCompute, pollCompute } from "../api/client";
import { useEnrichmentStore } from "../stores/enrichmentStore";

export interface ComputeJobState {
  status: "idle" | "running" | "complete" | "error";
  progress: number; // 0.0 – 1.0
  error: string | null;
}

export function useComputeJob(speaker: string) {
  const [state, setState] = useState<ComputeJobState>({
    status: "idle",
    progress: 0,
    error: null,
  });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const load = useEnrichmentStore((s) => s.load);

  const clearPoll = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // Clear interval on unmount
  useEffect(() => () => { clearPoll(); }, [clearPoll]);

  const start = useCallback(async (): Promise<void> => {
    clearPoll();
    setState({ status: "running", progress: 0, error: null });

    let jobId: string;
    try {
      const job = await startCompute(speaker);
      jobId = job.job_id;
    } catch (e) {
      setState({ status: "error", progress: 0, error: String(e) });
      return;
    }

    intervalRef.current = setInterval(async () => {
      try {
        const poll = await pollCompute(speaker, jobId);
        setState((prev) => ({ ...prev, progress: poll.progress ?? prev.progress }));

        if (poll.status === "complete") {
          clearPoll();
          await load();
          setState({ status: "complete", progress: 1, error: null });
        } else if (poll.status === "error") {
          clearPoll();
          setState({ status: "error", progress: 0, error: poll.message ?? "Compute failed" });
        }
      } catch (e) {
        clearPoll();
        setState({ status: "error", progress: 0, error: String(e) });
      }
    }, 1000);
  }, [speaker, load, clearPoll]);

  return { start, state };
}
