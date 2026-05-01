// @vitest-environment jsdom
import { renderHook, act, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("../../api/client", () => ({
  startCompute: vi.fn(),
  pollCompute: vi.fn(),
  cancelComputeJob: vi.fn(),
}));

import { startCompute, pollCompute, cancelComputeJob } from "../../api/client";
import { pollBatchSpeakerJob } from "../batch-pipeline/useBatchJobPoll";
import { useBatchPipelineJob } from "../useBatchPipelineJob";
import type { BatchRunRequest } from "../useBatchPipelineJob";

const mockStart = startCompute as unknown as ReturnType<typeof vi.fn>;
const mockPoll = pollCompute as unknown as ReturnType<typeof vi.fn>;
const mockCancelComputeJob = cancelComputeJob as unknown as ReturnType<typeof vi.fn>;

function baseRequest(speakers: string[]): BatchRunRequest {
  return {
    speakers,
    steps: ["normalize", "stt", "ortho", "ipa"],
    overwrites: {},
  };
}

/** Drain micro-/macrotasks while real timers are active. Each call flushes
 *  the Promise queue plus one tick of the poll-loop `setTimeout`. */
async function flushAsync(times = 20) {
  for (let i = 0; i < times; i += 1) {
    await Promise.resolve();
    await new Promise((r) => setTimeout(r, 0));
  }
}

describe("useBatchPipelineJob", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCancelComputeJob.mockResolvedValue({ cancelled: true, job_id: "job-A" });
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("pollBatchSpeakerJob returns cancelled without fetching when cancellation is already requested", async () => {
    const onProgress = vi.fn();

    const outcome = await pollBatchSpeakerJob("job-A", () => true, onProgress, () => true);

    expect(outcome).toEqual({
      pollErrored: false,
      pollResult: null,
      pollErrorMessage: null,
      pollCancelled: true,
    });
    expect(mockPoll).not.toHaveBeenCalled();
    expect(onProgress).not.toHaveBeenCalled();
  });

  it("runs speakers sequentially in request order", async () => {
    const startOrder: string[] = [];
    // Gate each speaker's poll so we can observe sequencing.
    const releases: Record<string, () => void> = {};
    const pending: Record<string, Promise<void>> = {};
    for (const s of ["A", "B", "C"]) {
      pending[s] = new Promise<void>((r) => {
        releases[s] = r;
      });
    }
    let counter = 0;
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => {
      const speaker = String(body.speaker);
      startOrder.push(speaker);
      counter += 1;
      return { job_id: `job-${speaker}-${counter}` };
    });
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      // e.g. job-A-1 -> A
      const speaker = jobId.split("-")[1];
      await pending[speaker];
      return { status: "complete", progress: 1, result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } } };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A", "B", "C"]));
      await flushAsync(5);
    });

    // A has started; B and C have not.
    expect(startOrder).toEqual(["A"]);

    await act(async () => {
      releases["A"]();
      await flushAsync(5);
    });
    expect(startOrder).toEqual(["A", "B"]);

    await act(async () => {
      releases["B"]();
      await flushAsync(5);
    });
    expect(startOrder).toEqual(["A", "B", "C"]);

    await act(async () => {
      releases["C"]();
      await runPromise;
    });

    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.outcomes.map((o) => o.status)).toEqual([
      "complete",
      "complete",
      "complete",
    ]);
  });

  it("per-speaker error doesn't abort batch", async () => {
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => {
      return { job_id: `job-${String(body.speaker)}` };
    });
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      if (speaker === "B") {
        return { status: "error", progress: 0.5, error: "boom" };
      }
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run(baseRequest(["A", "B", "C"]));
    });

    expect(mockStart).toHaveBeenCalledTimes(3);
    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.outcomes[0].status).toBe("complete");
    expect(result.current.state.outcomes[1].status).toBe("error");
    expect(result.current.state.outcomes[1].error).toBe("boom");
    expect(result.current.state.outcomes[2].status).toBe("complete");
  });

  it("startCompute rejection doesn't abort batch", async () => {
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => {
      const speaker = String(body.speaker);
      if (speaker === "A") {
        throw new Error("start exploded");
      }
      return { job_id: `job-${speaker}` };
    });
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run(baseRequest(["A", "B", "C"]));
    });

    expect(mockStart).toHaveBeenCalledTimes(3);
    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.outcomes[0].status).toBe("error");
    expect(result.current.state.outcomes[0].error).toBe("start exploded");
    expect(result.current.state.outcomes[1].status).toBe("complete");
    expect(result.current.state.outcomes[2].status).toBe("complete");
  });

  it("progress updates reflect poll responses", async () => {
    mockStart.mockResolvedValue({ job_id: "job-A" });
    let callCount = 0;
    mockPoll.mockImplementation(async () => {
      callCount += 1;
      if (callCount === 1) {
        return { status: "running", progress: 42, message: "Loading model" };
      }
      return {
        status: "complete",
        progress: 1,
        result: { speaker: "A", steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A"]));
      // Let the first poll (status:running) land.
      await flushAsync(5);
    });

    expect(result.current.state.currentProgress).toBeCloseTo(0.42, 5);
    expect(result.current.state.currentMessage).toBe("Loading model");

    await act(async () => {
      await runPromise;
    });

    expect(result.current.state.status).toBe("complete");
  });

  it("preserves the started job id when polling loses API connectivity", async () => {
    mockStart.mockResolvedValue({ job_id: "job-A" });
    mockPoll.mockRejectedValue(
      new Error(
        "Could not reach the PARSE API for POST /api/compute/full_pipeline/status.",
      ),
    );

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run(baseRequest(["A"]));
    });

    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.outcomes[0]).toMatchObject({
      speaker: "A",
      status: "error",
      error:
        "Could not reach the PARSE API for POST /api/compute/full_pipeline/status.",
      jobId: "job-A",
      errorPhase: "poll",
    });
  });

  it("final state after all complete", async () => {
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => ({
      job_id: `job-${String(body.speaker)}`,
    }));
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run(baseRequest(["A", "B", "C"]));
    });

    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.currentSpeaker).toBeNull();
    expect(result.current.state.currentSpeakerIndex).toBeNull();
    expect(result.current.state.currentSubJobId).toBeNull();
    expect(result.current.state.currentProgress).toBe(0);
    expect(result.current.state.currentMessage).toBeNull();
    expect(result.current.state.completedSpeakers).toBe(3);
    expect(result.current.state.outcomes.every((o) => o.status === "complete")).toBe(true);
    expect(result.current.state.cancelled).toBe(false);
  });

  it("cancel() marks the current speaker cancelled instead of complete", async () => {
    // Control A's poll completion manually so we can cancel while A is mid-run.
    const releases: Record<string, () => void> = {};
    const pending: Record<string, Promise<void>> = {};
    for (const s of ["A", "B", "C"]) {
      pending[s] = new Promise<void>((r) => {
        releases[s] = r;
      });
    }
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => ({
      job_id: `job-${String(body.speaker)}`,
    }));
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      await pending[speaker];
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A", "B", "C"]));
      await flushAsync(5);
    });

    // A is in-flight.
    expect(result.current.state.currentSpeaker).toBe("A");

    // Request cancel while A is running.
    await act(async () => {
      result.current.cancel();
      await flushAsync(2);
    });
    expect(result.current.state.status).toBe("cancelling");

    // A completes server-side after cancellation — the UI must discard that
    // successful late result and mark A cancelled, then skip B/C.
    await act(async () => {
      releases["A"]();
      await runPromise;
    });

    expect(mockStart).toHaveBeenCalledTimes(1); // ONLY A got started
    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.cancelled).toBe(true);
    expect(result.current.state.outcomes[0].status).toBe("cancelled");
    expect(result.current.state.outcomes[1].status).toBe("cancelled");
    expect(result.current.state.outcomes[2].status).toBe("cancelled");
  });

  it("cancel() fires backend cancel when a compute job is active", async () => {
    let releasePoll!: () => void;
    const pollPending = new Promise<void>((resolve) => {
      releasePoll = resolve;
    });
    mockStart.mockResolvedValue({ job_id: "job-A" });
    mockPoll.mockImplementation(async () => {
      await pollPending;
      return { status: "complete", progress: 1, result: { speaker: "A", steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } } };
    });
    mockCancelComputeJob.mockResolvedValue({ cancelled: true, job_id: "job-A" });

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A"]));
      await flushAsync(5);
    });

    expect(result.current.state.currentSubJobId).toBe("job-A");

    await act(async () => {
      result.current.cancel();
      await flushAsync(2);
    });

    expect(mockCancelComputeJob).toHaveBeenCalledTimes(1);
    expect(mockCancelComputeJob).toHaveBeenCalledWith("job-A");

    await act(async () => {
      releasePoll();
      await runPromise;
    });
  });

  it("cancel() skips backend cancel when no compute job is active", async () => {
    let releaseStart!: () => void;
    const startPending = new Promise<void>((resolve) => {
      releaseStart = resolve;
    });
    mockStart.mockImplementation(async () => {
      await startPending;
      return { job_id: "job-A" };
    });
    mockPoll.mockResolvedValue({ status: "complete", progress: 1, result: { speaker: "A", steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } } });

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A"]));
      await flushAsync(2);
    });

    expect(result.current.state.currentSubJobId).toBeNull();

    await act(async () => {
      result.current.cancel();
      await flushAsync(2);
    });

    expect(mockCancelComputeJob).not.toHaveBeenCalled();

    await act(async () => {
      releaseStart();
      await runPromise;
    });
  });

  it("cancel() survives backend cancel helper rejection", async () => {
    let releasePoll!: () => void;
    const pollPending = new Promise<void>((resolve) => {
      releasePoll = resolve;
    });
    mockStart.mockResolvedValue({ job_id: "job-A" });
    mockPoll.mockImplementation(async () => {
      await pollPending;
      return { status: "complete", progress: 1, result: { speaker: "A", steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } } };
    });
    mockCancelComputeJob.mockRejectedValue(new Error("cancel endpoint unavailable"));

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A", "B"]));
      await flushAsync(5);
    });

    await act(async () => {
      expect(() => result.current.cancel()).not.toThrow();
      await flushAsync(2);
    });

    expect(result.current.state.status).toBe("cancelling");

    await act(async () => {
      releasePoll();
      await runPromise;
    });

    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.cancelled).toBe(true);
    expect(result.current.state.outcomes.map((outcome) => outcome.status)).toEqual(["cancelled", "cancelled"]);
  });

  it("cancel() short-circuits the polling loop on the next poll tick", async () => {
    vi.useFakeTimers();
    mockStart.mockResolvedValue({ job_id: "job-A" });
    mockPoll.mockResolvedValue({ status: "running", progress: 0.2, message: "Still running" });

    const { result } = renderHook(() => useBatchPipelineJob());

    let runPromise!: Promise<void>;
    await act(async () => {
      runPromise = result.current.run(baseRequest(["A", "B", "C"]));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockPoll).toHaveBeenCalledTimes(1);
    expect(result.current.state.currentSpeaker).toBe("A");

    await act(async () => {
      result.current.cancel();
      await Promise.resolve();
    });
    expect(result.current.state.status).toBe("cancelling");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
      await runPromise;
    });

    expect(mockPoll).toHaveBeenCalledTimes(1);
    expect(mockStart).toHaveBeenCalledTimes(1);
    expect(result.current.state.status).toBe("complete");
    expect(result.current.state.cancelled).toBe(true);
    expect(result.current.state.outcomes.map((outcome) => outcome.status)).toEqual([
      "cancelled",
      "cancelled",
      "cancelled",
    ]);
  });

  it("stepsBySpeaker overrides the default steps for that speaker", async () => {
    // Speaker B only gets the ORTH step; A and C get the full list.
    const bodies: Record<string, unknown>[] = [];
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => {
      bodies.push(body);
      return { job_id: `job-${String(body.speaker)}` };
    });
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run({
        speakers: ["A", "B", "C"],
        steps: ["normalize", "stt", "ortho", "ipa"],
        overwrites: {},
        stepsBySpeaker: { B: ["ortho"] },
      });
    });

    // Every speaker's step list reflects the per-speaker override.
    const bodyFor = (s: string) => bodies.find((b) => b.speaker === s);
    expect(bodyFor("A")?.steps).toEqual(["normalize", "stt", "ortho", "ipa"]);
    expect(bodyFor("B")?.steps).toEqual(["ortho"]);
    expect(bodyFor("C")?.steps).toEqual(["normalize", "stt", "ortho", "ipa"]);
  });

  it("forwards run_mode to the full_pipeline start body", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => {
      bodies.push(body);
      return { job_id: `job-${String(body.speaker)}` };
    });
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run({
        speakers: ["A", "B", "C"],
        steps: ["stt"],
        overwrites: {},
        runMode: "edited-only",
      });
    });

    expect(bodies.map((body) => body.run_mode)).toEqual(["edited-only", "edited-only", "edited-only"]);
  });

  it("stepsBySpeaker with empty array marks speaker cancelled without calling backend", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockStart.mockImplementation(async (_type: string, body: Record<string, unknown>) => {
      bodies.push(body);
      return { job_id: `job-${String(body.speaker)}` };
    });
    mockPoll.mockImplementation(async (_type: string, jobId: string) => {
      const speaker = jobId.replace("job-", "");
      return {
        status: "complete",
        progress: 1,
        result: { speaker, steps_run: [], results: {}, summary: { ok: 0, skipped: 0, error: 0 } },
      };
    });

    const { result } = renderHook(() => useBatchPipelineJob());

    await act(async () => {
      await result.current.run({
        speakers: ["A", "B", "C"],
        steps: ["ortho"],
        overwrites: {},
        stepsBySpeaker: { B: [] },
      });
    });

    // B was skipped client-side; only A and C hit the backend.
    expect(bodies.map((b) => b.speaker)).toEqual(["A", "C"]);
    expect(result.current.state.outcomes[0].status).toBe("complete");
    expect(result.current.state.outcomes[1].status).toBe("cancelled");
    expect(result.current.state.outcomes[2].status).toBe("complete");
  });
});
