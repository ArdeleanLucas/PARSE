// @vitest-environment jsdom
import { renderHook, act, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ActiveJobSnapshot } from "../../api/contracts/job-observability";
import { listActiveJobs } from "../../api/client";
import { useActiveJobsFeed } from "../useActiveJobsFeed";

vi.mock("../../api/client", () => ({
  listActiveJobs: vi.fn(),
}));

const runningJob = (jobId = "job-1"): ActiveJobSnapshot => ({
  jobId,
  type: "compute:lexeme_rerun_ortho",
  status: "running",
  progress: 0.4,
});

function setVisibilityState(value: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    value,
    configurable: true,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("useActiveJobsFeed", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(listActiveJobs).mockResolvedValue([runningJob()]);
    setVisibilityState("visible");
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("polls on the fast cadence while active jobs are present", async () => {
    renderHook(() => useActiveJobsFeed());

    await act(async () => {
      await Promise.resolve();
    });
    expect(listActiveJobs).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(listActiveJobs).toHaveBeenCalledTimes(2);
  });

  it("drops to a slow heartbeat when empty, then resumes fast cadence after a non-empty response", async () => {
    vi.mocked(listActiveJobs)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([runningJob("job-2")])
      .mockResolvedValueOnce([runningJob("job-2")]);

    renderHook(() => useActiveJobsFeed());

    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(listActiveJobs).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(listActiveJobs).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(listActiveJobs).toHaveBeenCalledTimes(3);
  });

  it("pauses while the document is hidden and resumes when visible", async () => {
    renderHook(() => useActiveJobsFeed());

    await act(async () => {
      await Promise.resolve();
    });
    act(() => setVisibilityState("hidden"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(listActiveJobs).toHaveBeenCalledTimes(1);

    act(() => setVisibilityState("visible"));
    await act(async () => {
      await Promise.resolve();
    });
    expect(listActiveJobs).toHaveBeenCalledTimes(2);
  });

  it("treats network failures as an empty transient state", async () => {
    vi.mocked(listActiveJobs).mockRejectedValueOnce(new Error("offline"));

    const { result } = renderHook(() => useActiveJobsFeed());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.jobs).toEqual([]);
  });

  it("refresh triggers an immediate fetch independent of the timer", async () => {
    const { result } = renderHook(() => useActiveJobsFeed());

    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await result.current.refresh();
    });

    expect(listActiveJobs).toHaveBeenCalledTimes(2);
  });
});
