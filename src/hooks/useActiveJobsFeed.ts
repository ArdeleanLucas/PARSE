import { useCallback, useEffect, useRef, useState } from "react";
import { listActiveJobs } from "../api/client";
import type { ActiveJobSnapshot } from "../api/contracts/job-observability";

const FAST_POLL_MS = 1000;
const SLOW_POLL_MS = 10_000;
export const ACTIVE_JOBS_REFRESH_EVENT = "parse:active-jobs-refresh";

function hasNonTerminalJob(jobs: ActiveJobSnapshot[]): boolean {
  return jobs.some((job) => {
    const status = job.status.toLowerCase();
    return status !== "complete" && status !== "completed" && status !== "done" && status !== "error" && status !== "failed" && status !== "cancelled" && status !== "canceled";
  });
}

function sameJobs(a: ActiveJobSnapshot[], b: ActiveJobSnapshot[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((job, index) => {
    const other = b[index];
    return other != null
      && job.jobId === other.jobId
      && job.type === other.type
      && job.status === other.status
      && job.progress === other.progress
      && job.message === other.message
      && job.error === other.error
      && job.etaMs === other.etaMs
      && job.startedTs === other.startedTs;
  });
}

export function useActiveJobsFeed(): { jobs: ActiveJobSnapshot[]; refresh: () => Promise<void> } {
  const [jobs, setJobs] = useState<ActiveJobSnapshot[]>([]);
  const [pollMs, setPollMs] = useState(FAST_POLL_MS);
  const pollMsRef = useRef(FAST_POLL_MS);
  const hiddenRef = useRef(typeof document !== "undefined" ? document.visibilityState === "hidden" : false);
  const inFlightRef = useRef(false);

  useEffect(() => {
    pollMsRef.current = pollMs;
  }, [pollMs]);

  const updatePollMs = useCallback((nextPollMs: number) => {
    pollMsRef.current = nextPollMs;
    setPollMs(nextPollMs);
  }, []);

  const refresh = useCallback(async () => {
    if (hiddenRef.current || inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const nextJobs = await listActiveJobs();
      setJobs((previous) => sameJobs(previous, nextJobs) ? previous : nextJobs);
      updatePollMs(nextJobs.length > 0 && hasNonTerminalJob(nextJobs) ? FAST_POLL_MS : SLOW_POLL_MS);
    } catch {
      setJobs((previous) => previous.length === 0 ? previous : []);
      updatePollMs(SLOW_POLL_MS);
    } finally {
      inFlightRef.current = false;
    }
  }, [updatePollMs]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    let timerId: number | null = null;

    const tick = async () => {
      if (cancelled) return;
      // Await the refresh before scheduling the next timer so slow network
      // responses cannot create overlapping active-jobs fetches, and the
      // next delay observes any fast/slow cadence update from the response.
      if (!hiddenRef.current) {
        await refresh();
      }
      if (cancelled) return;
      timerId = window.setTimeout(tick, pollMsRef.current);
    };

    timerId = window.setTimeout(tick, pollMsRef.current);
    return () => {
      cancelled = true;
      if (timerId !== null) {
        window.clearTimeout(timerId);
      }
    };
  }, [pollMs, refresh]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      hiddenRef.current = document.visibilityState === "hidden";
      if (!hiddenRef.current) {
        updatePollMs(FAST_POLL_MS);
        void refresh();
      }
    };
    const handleExternalRefresh = () => {
      if (hiddenRef.current) return;
      updatePollMs(FAST_POLL_MS);
      void refresh();
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener(ACTIVE_JOBS_REFRESH_EVENT, handleExternalRefresh);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener(ACTIVE_JOBS_REFRESH_EVENT, handleExternalRefresh);
    };
  }, [refresh, updatePollMs]);

  return { jobs, refresh };
}
