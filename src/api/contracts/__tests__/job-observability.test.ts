// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listActiveJobs } from "../job-observability";

const fetchSpy = vi.spyOn(globalThis, "fetch");

function activeJobsResponse(job: Record<string, unknown>) {
  return new Response(JSON.stringify({ jobs: [job] }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function baseJob(overrides: Record<string, unknown> = {}) {
  return {
    job_id: "job-1",
    type: "compute:lexeme_rerun_ortho",
    status: "running",
    message: "Tagged rerun loading ORTH provider",
    eta_ms: 12_000,
    started_ts: 1_716_000_000,
    error: "recoverable warning",
    ...overrides,
  };
}

beforeEach(() => {
  fetchSpy.mockReset();
});

afterEach(() => {
  fetchSpy.mockReset();
});

describe("listActiveJobs progress normalization", () => {
  it.each([
    { raw: 0, expected: 0, label: "0%" },
    { raw: 50, expected: 0.5, label: "50%" },
    { raw: 100, expected: 1, label: "100%" },
    // Khan02 tagged-only ORTH repro: first provider-load emit was 2.0% and rendered as 100% before normalization.
    { raw: 2, expected: 0.02, label: "2%" },
    { raw: 150, expected: 1, label: "150% clamped" },
    { raw: -10, expected: 0, label: "-10% clamped" },
    { raw: undefined, expected: 0, label: "missing" },
  ])("normalizes backend wire progress $label to a 0-1 snapshot fraction", async ({ raw, expected }) => {
    const job = baseJob(raw === undefined ? {} : { progress: raw });
    fetchSpy.mockResolvedValueOnce(activeJobsResponse(job));

    const [snapshot] = await listActiveJobs();

    expect(fetchSpy).toHaveBeenCalledWith("/api/jobs/active", expect.any(Object));
    expect(snapshot.progress).toBe(expected);
  });

  it("keeps non-progress fields stable while normalizing progress", async () => {
    fetchSpy.mockResolvedValueOnce(activeJobsResponse(baseJob({
      jobId: "camel-job",
      job_id: undefined,
      progress: 25,
      etaMs: 4_200,
      startedTs: 1_716_000_123,
      speaker: " Khan02 ",
      language: " sdh ",
    })));

    const [snapshot] = await listActiveJobs();

    expect(snapshot).toEqual({
      jobId: "camel-job",
      type: "compute:lexeme_rerun_ortho",
      status: "running",
      progress: 0.25,
      message: "Tagged rerun loading ORTH provider",
      etaMs: 4_200,
      startedTs: 1_716_000_123,
      error: "recoverable warning",
      speaker: "Khan02",
      language: "sdh",
    });
  });
});
