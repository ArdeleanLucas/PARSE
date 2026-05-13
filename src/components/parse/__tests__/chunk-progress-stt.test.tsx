// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ActiveJobSnapshot } from "../../../api/contracts/job-observability";
import { HeaderJobStrip, chunkInfoFromMessage } from "../HeaderJobStrip";

const baseJob = (overrides: Partial<ActiveJobSnapshot> = {}): ActiveJobSnapshot => ({
  jobId: "stt-job-1",
  type: "compute:stt",
  status: "running",
  progress: 0.42,
  message: "STT chunk 3/7 (1200s–1800s)",
  ...overrides,
});

describe("HeaderJobStrip STT chunk-progress contract", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders STT chunk progress from the same chunk message shape used by ORTH jobs", () => {
    const orthoJob = baseJob({
      jobId: "orth-chunk",
      type: "compute:ortho",
      progress: 0.42,
      message: "ORTH chunk 3/7 (1200s–1800s)",
    });
    const sttJob = baseJob({
      jobId: "stt-chunk",
      type: "compute:stt",
      progress: 0.42,
      message: "STT chunk 3/7 (1200s–1800s)",
    });

    render(<HeaderJobStrip jobs={[orthoJob, sttJob]} />);

    const orthoRow = screen.getByTestId("topbar-job-strip-row-orth-chunk");
    const sttRow = screen.getByTestId("topbar-job-strip-row-stt-chunk");
    expect(within(orthoRow).getByText("ORTH")).toBeTruthy();
    expect(within(sttRow).getByText("STT")).toBeTruthy();
    expect(within(orthoRow).getByText("42%")).toBeTruthy();
    expect(within(sttRow).getByText("42%")).toBeTruthy();
    expect(within(orthoRow).getByTestId("chunk-progress-overlay").textContent).toBe("Chunk 3 of 7");
    expect(within(sttRow).getByTestId("chunk-progress-overlay").textContent).toBe("Chunk 3 of 7");
    expect(within(sttRow).getByTestId("chunk-progress-overlay").className).toBe(
      within(orthoRow).getByTestId("chunk-progress-overlay").className,
    );
    expect(sttRow).toMatchInlineSnapshot(`
      <div
        class="flex items-center gap-2 rounded-md border px-2.5 py-1 text-[11px] border-indigo-200 bg-indigo-50"
        data-testid="topbar-job-strip-row-stt-chunk"
      >
        <svg
          aria-hidden="true"
          class="lucide lucide-loader-circle h-3 w-3 shrink-0 animate-spin text-indigo-600"
          fill="none"
          height="24"
          stroke="currentColor"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          viewBox="0 0 24 24"
          width="24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M21 12a9 9 0 1 1-6.219-8.56"
          />
        </svg>
        <span
          class="font-medium text-indigo-900"
        >
          STT
        </span>
        <div
          class="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-indigo-100"
        >
          <div
            class="h-full rounded-full bg-indigo-500 transition-all duration-300"
            data-testid="topbar-job-progress-stt-chunk"
            style="width: 42%;"
          />
        </div>
        <span
          class="tabular-nums text-indigo-700"
        >
          42
          %
        </span>
        <span
          class="rounded-sm bg-indigo-100 px-1.5 py-0.5 font-medium tabular-nums text-indigo-800"
          data-testid="chunk-progress-overlay"
          title="STT chunk 3/7 (1200s–1800s)"
        >
          Chunk 3 of 7
        </span>
        <button
          aria-label="Cancel stt-chunk"
          class="rounded border border-indigo-300 bg-white px-1.5 py-0.5 font-semibold text-indigo-700 hover:bg-indigo-100"
        >
          Cancel
        </button>
      </div>
    `);
  });

  it("renders failed STT chunk payloads with the same error affordance as failed ORTH payloads", () => {
    const orthoFailure = baseJob({
      jobId: "orth-failed-chunk",
      type: "compute:ortho",
      status: "error",
      progress: 0.28,
      message: "ORTH chunk 2/7 (600s–1200s)",
      error: "Chunk 2 failed: CUDA OOM",
    });
    const sttFailure = baseJob({
      jobId: "stt-failed-chunk",
      type: "compute:stt",
      status: "error",
      progress: 0.28,
      message: "STT chunk 2/7 (600s–1200s)",
      error: "Chunk 2 failed: CUDA OOM",
    });

    render(<HeaderJobStrip jobs={[orthoFailure, sttFailure]} />);

    const orthoRow = screen.getByTestId("topbar-job-strip-row-orth-failed-chunk");
    const sttRow = screen.getByTestId("topbar-job-strip-row-stt-failed-chunk");
    expect(within(orthoRow).getByText("ORTH failed")).toBeTruthy();
    expect(within(sttRow).getByText("STT failed")).toBeTruthy();
    expect(within(sttRow).getByTestId("topbar-job-error-stt-failed-chunk").textContent).toBe(
      within(orthoRow).getByTestId("topbar-job-error-orth-failed-chunk").textContent,
    );
    expect(sttRow.className).toBe(orthoRow.className);
    expect(within(sttRow).queryByTestId("chunk-progress-overlay")).toBeNull();
  });

  it("parses STT/ORTH-prefixed chunk messages and plain legacy chunk messages", () => {
    expect(chunkInfoFromMessage("STT chunk 3/7 (1200s–1800s)")).toEqual({ current: 3, total: 7 });
    expect(chunkInfoFromMessage("ORTH chunk 3/7 (1200s-1800s)")).toEqual({ current: 3, total: 7 });
    expect(chunkInfoFromMessage("Chunk 3/7 (1200s-1800s)")).toEqual({ current: 3, total: 7 });
  });
});
