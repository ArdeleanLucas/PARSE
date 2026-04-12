// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useActionJob } from "../useActionJob";

describe("useActionJob", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts in idle state", () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j1" });
    const poll = vi.fn().mockResolvedValue({ status: "running", progress: 0.1 });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    expect(result.current.state).toEqual({
      status: "idle",
      progress: 0,
      error: null,
      label: null,
    });
  });

  it("transitions to running on run()", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j1" });
    const poll = vi.fn().mockResolvedValue({ status: "running", progress: 0.3 });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      await result.current.run();
    });

    expect(result.current.state.status).toBe("running");
    expect(result.current.state.progress).toBe(0);
    expect(result.current.state.label).toBe("Running action…");
  });

  it("transitions to complete when poll returns done", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j2" });
    const poll = vi.fn().mockResolvedValue({ status: "done", progress: 100 });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Normalizing audio…",
      }),
    );

    await act(async () => {
      await result.current.run();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.progress).toBe(1);
  });

  it("transitions to error when poll returns failed", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j3" });
    const poll = vi.fn().mockResolvedValue({
      status: "failed",
      progress: 0.4,
      message: "Out of memory",
    });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running pipeline…",
      }),
    );

    await act(async () => {
      await result.current.run();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toBe("Out of memory");
  });

  it("calls onComplete callback on success", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j4" });
    const poll = vi.fn().mockResolvedValue({ status: "complete", progress: 1 });
    const onComplete = vi.fn().mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running STT…",
        onComplete,
      }),
    );

    await act(async () => {
      await result.current.run();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("normalizes progress > 1 as percentage", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j5" });
    const poll = vi.fn().mockResolvedValue({ status: "running", progress: 68 });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      await result.current.run();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.status).toBe("running");
    expect(result.current.state.progress).toBe(0.68);
  });

  it("cleans up polling interval on unmount", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j6" });
    const poll = vi.fn().mockResolvedValue({ status: "running", progress: 0.5 });
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");

    const { result, unmount } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      await result.current.run();
    });

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  it("reset() returns to idle and clears error", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j7" });
    const poll = vi.fn().mockResolvedValue({
      status: "error",
      progress: 0.2,
      message: "Bad request",
    });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      await result.current.run();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.state.status).toBe("error");

    act(() => {
      result.current.reset();
    });

    expect(result.current.state).toEqual({
      status: "idle",
      progress: 0,
      error: null,
      label: null,
    });
  });

  it("run() is a no-op when already running", async () => {
    const start = vi.fn().mockResolvedValue({ job_id: "j8" });
    const poll = vi.fn().mockResolvedValue({ status: "running", progress: 0.2 });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      await result.current.run();
    });

    await act(async () => {
      await result.current.run();
    });

    expect(start).toHaveBeenCalledTimes(1);
    expect(result.current.state.status).toBe("running");
  });

  it("ignores concurrent run() calls while start() is still resolving", async () => {
    let releaseStart: (() => void) | null = null;
    const start = vi.fn(
      () =>
        new Promise<{ job_id: string }>((resolve) => {
          releaseStart = () => resolve({ job_id: "j9" });
        }),
    );
    const poll = vi.fn().mockResolvedValue({ status: "running", progress: 0.2 });

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      const firstRun = result.current.run();
      const secondRun = result.current.run();
      expect(start).toHaveBeenCalledTimes(1);
      releaseStart?.();
      await firstRun;
      await secondRun;
    });

    expect(start).toHaveBeenCalledTimes(1);
    expect(result.current.state.status).toBe("running");
  });

  it("surfaces start failures immediately without polling", async () => {
    const start = vi.fn().mockRejectedValue(new Error("Start failed"));
    const poll = vi.fn();

    const { result } = renderHook(() =>
      useActionJob({
        start,
        poll,
        label: "Running action…",
      }),
    );

    await act(async () => {
      await result.current.run();
    });

    expect(result.current.state).toEqual({
      status: "error",
      progress: 0,
      error: "Start failed",
      label: "Running action…",
    });
    expect(poll).not.toHaveBeenCalled();
  });
});
