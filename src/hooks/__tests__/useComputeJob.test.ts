// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useComputeJob } from "../useComputeJob";

vi.mock("../../api/client", () => ({
  startCompute: vi.fn(),
  pollCompute: vi.fn(),
}));

const mockLoad = vi.fn().mockResolvedValue(undefined);
vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: vi.fn((sel: (s: { load: () => Promise<void> }) => unknown) =>
    sel({ load: mockLoad })
  ),
}));

import { startCompute, pollCompute } from "../../api/client";

describe("useComputeJob", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });
  afterEach(() => { vi.useRealTimers(); });

  it("sets status to running after start() is called", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "j1" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "running", progress: 0.1 });
    const { result } = renderHook(() => useComputeJob("Fail01"));
    await act(async () => { await result.current.start(); });
    expect(result.current.state.status).toBe("running");
  });

  it("sets status to complete when poll returns complete", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "j2" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "complete", progress: 1 });
    const { result } = renderHook(() => useComputeJob("Fail01"));
    await act(async () => {
      await result.current.start();
      await vi.runAllTimersAsync();
    });
    expect(result.current.state.status).toBe("complete");
  });

  it("calls enrichmentStore.load() on complete", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "j3" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "complete", progress: 1 });
    const { result } = renderHook(() => useComputeJob("Fail01"));
    await act(async () => {
      await result.current.start();
      await vi.runAllTimersAsync();
    });
    expect(mockLoad).toHaveBeenCalledOnce();
  });

  it("sets status to error when poll returns error", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "j4" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "error", progress: 0, message: "Compute failed" });
    const { result } = renderHook(() => useComputeJob("Fail01"));
    await act(async () => {
      await result.current.start();
      await vi.runAllTimersAsync();
    });
    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toBe("Compute failed");
  });

  it("clears polling interval on unmount", async () => {
    vi.mocked(startCompute).mockResolvedValue({ job_id: "j5" });
    vi.mocked(pollCompute).mockResolvedValue({ status: "running", progress: 0.5 });
    const clearSpy = vi.spyOn(globalThis, "clearInterval");
    const { result, unmount } = renderHook(() => useComputeJob("Fail01"));
    await act(async () => { await result.current.start(); });
    unmount();
    expect(clearSpy).toHaveBeenCalled();
  });
});
