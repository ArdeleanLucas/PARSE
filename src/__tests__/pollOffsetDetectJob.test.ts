import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// The client uses a bare ``fetch`` wrapper. Mock the global fetch so
// each polling iteration resolves against a scripted queue of /api
// responses. That way we exercise the full pollOffsetDetectJob branch
// surface — progress callback, success, error-with-traceback — without
// standing up a server.

import { pollOffsetDetectJob, OffsetJobError } from "../api/client";

type ScriptedResponse = {
  status: number;
  body: unknown;
};

function queueResponses(responses: ScriptedResponse[]): () => void {
  const queue = [...responses];
  const impl = vi.fn(async () => {
    const next = queue.shift();
    if (!next) {
      throw new Error("fetch called more times than scripted");
    }
    return new Response(JSON.stringify(next.body), {
      status: next.status,
      headers: { "Content-Type": "application/json" },
    });
  });
  const original = globalThis.fetch;
  (globalThis as { fetch: typeof fetch }).fetch = impl as unknown as typeof fetch;
  return () => {
    (globalThis as { fetch: typeof fetch }).fetch = original;
  };
}

describe("pollOffsetDetectJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("resolves with the backend OffsetDetectResult on complete and fires onProgress for each poll", async () => {
    const cleanup = queueResponses([
      { status: 200, body: { status: "running", progress: 30, message: "Selecting anchors" } },
      {
        status: 200,
        body: {
          status: "complete",
          progress: 100,
          result: {
            speaker: "Fail02",
            offsetSec: -1.23,
            confidence: 0.9,
            nAnchors: 5,
            totalAnchors: 6,
            totalSegments: 200,
            method: "monotonic",
          },
        },
      },
    ]);
    try {
      const progressCalls: Array<{ progress: number; message?: string }> = [];
      const promise = pollOffsetDetectJob("job-1", "offset_detect", {
        intervalMs: 10,
        onProgress: (p) => progressCalls.push(p),
      });
      // Two polls → two 10ms waits → advance the fake clock enough.
      await vi.advanceTimersByTimeAsync(25);
      const result = await promise;
      expect(result.offsetSec).toBe(-1.23);
      expect(progressCalls.length).toBeGreaterThanOrEqual(1);
      expect(progressCalls[0]?.message).toBe("Selecting anchors");
    } finally {
      cleanup();
    }
  });

  it("throws OffsetJobError carrying the backend traceback when status=error", async () => {
    const cleanup = queueResponses([
      {
        status: 200,
        body: {
          status: "error",
          progress: 55,
          error: "No STT segments available.",
          traceback: "Traceback (most recent call last):\n  File server.py, line 4850\nValueError: No STT segments available.",
        },
      },
    ]);
    try {
      // Swallow the rejection exactly once — chaining .catch on the
      // same promise we later assert on would count as a second
      // settlement and trigger an unhandled-rejection warning in
      // vitest.
      const settled: Promise<unknown> = pollOffsetDetectJob("job-2", "offset_detect", {
        intervalMs: 5,
      }).then(
        () => {
          throw new Error("expected rejection");
        },
        (err) => err,
      );
      await vi.advanceTimersByTimeAsync(15);
      const caught = await settled;
      expect(caught).toBeInstanceOf(OffsetJobError);
      const oe = caught as OffsetJobError;
      expect(oe.jobId).toBe("job-2");
      expect(oe.message).toContain("No STT segments");
      expect(oe.traceback).toContain("Traceback");
    } finally {
      cleanup();
    }
  });
});
