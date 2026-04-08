// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useComputeJob } from "../useComputeJob";

vi.mock("../../api/client", () => ({
  startCompute: vi.fn(),
  pollCompute: vi.fn(),
}));

const mockLoad = vi.fn().mockResolvedValue(undefined);
vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (state: { load: () => Promise<void> }) => unknown) =>
    selector({ load: mockLoad }),
}));

import { startCompute, pollCompute } from "../../api/client";

describe("useComputeJob", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("sets status to running after start() is called", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "job-1" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "running", progress: 0.2 });

    const { result } = renderHook(() => useComputeJob("cognates"));

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.state.status).toBe("running");
    expect(result.current.state.progress).toBe(0);
  });

  it("sets status to complete when poll returns complete", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "job-2" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "complete", progress: 100 });

    const { result } = renderHook(() => useComputeJob("cognates"));

    await act(async () => {
      await result.current.start();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.progress).toBe(1);
  });

  it("calls enrichmentStore.load() on complete", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "job-3" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "complete", progress: 1 });

    const { result } = renderHook(() => useComputeJob("cognates"));

    await act(async () => {
      await result.current.start();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(mockLoad).toHaveBeenCalledOnce();
  });

  it("sets status to error when poll returns error", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "job-4" });
    vi.mocked(pollCompute).mockResolvedValue({
      status: "error",
      progress: 40,
      message: "Compute failed",
    });

    const { result } = renderHook(() => useComputeJob("cognates"));

    await act(async () => {
      await result.current.start();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toBe("Compute failed");
  });

  it("clears polling interval on unmount", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "job-5" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "running", progress: 50 });

    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
    const { result, unmount } = renderHook(() => useComputeJob("cognates"));

    await act(async () => {
      await result.current.start();
    });

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
  });
});
