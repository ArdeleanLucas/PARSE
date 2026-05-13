// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ActiveJobSnapshot } from "../../../api/contracts/job-observability";
import { HeaderJobStrip } from "../HeaderJobStrip";

const baseJob = (overrides: Partial<ActiveJobSnapshot> = {}): ActiveJobSnapshot => ({
  jobId: "stage-context-job",
  type: "compute:full_pipeline",
  status: "running",
  progress: 0.12,
  message: "STT chunk 3/19 (1200s–1800s)",
  ...overrides,
});

function renderSingleJob(overrides: Partial<ActiveJobSnapshot>) {
  const job = baseJob(overrides);
  render(<HeaderJobStrip jobs={[job]} />);
  return screen.getByTestId(`topbar-job-strip-row-${job.jobId}`);
}

describe("HeaderJobStrip stage context", () => {
  afterEach(() => cleanup());

  it("preserves STT prefix in chunk messages when the chip is Pipeline", () => {
    const row = renderSingleJob({
      jobId: "pipeline-stt-chunk",
      type: "compute:full_pipeline",
      message: "STT chunk 3/19 (1200s–1800s)",
    });

    expect(within(row).getByText("Pipeline")).toBeTruthy();
    expect(within(row).getByTestId("chunk-progress-overlay").textContent).toBe("STT chunk 3 of 19");
  });

  it("strips STT prefix in chunk messages when the chip is STT", () => {
    const row = renderSingleJob({
      jobId: "stt-chunk",
      type: "compute:stt",
      message: "STT chunk 3/19 (1200s–1800s)",
    });

    expect(within(row).getByText("STT")).toBeTruthy();
    expect(within(row).getByTestId("chunk-progress-overlay").textContent).toBe("Chunk 3 of 19");
  });

  it("preserves ORTH prefix in chunk messages when the chip is Pipeline", () => {
    const row = renderSingleJob({
      jobId: "pipeline-orth-chunk",
      type: "compute:full_pipeline",
      progress: 0.33,
      message: "ORTH chunk 5/12 (0s–600s)",
    });

    expect(within(row).getByText("Pipeline")).toBeTruthy();
    expect(within(row).getByTestId("chunk-progress-overlay").textContent).toBe("ORTH chunk 5 of 12");
  });

  it("preserves IPA prefix in callback messages when the chip is Pipeline", () => {
    const row = renderSingleJob({
      jobId: "pipeline-ipa-batch",
      type: "compute:full_pipeline",
      progress: 0.66,
      message: "IPA batch 4/8",
    });

    expect(row.textContent).toContain("Pipeline");
    expect(row.textContent).toContain("IPA batch 4/8");
  });

  it("preserves STT prefix in transcribing messages when the chip is Pipeline", () => {
    const row = renderSingleJob({
      jobId: "pipeline-stt-transcribing",
      type: "compute:full_pipeline",
      progress: 0.16,
      message: "STT transcribing (5 segments)",
    });

    expect(row.textContent).toContain("Pipeline");
    expect(row.textContent).toContain("STT transcribing (5 segments)");
  });

  it("renders messages with no stage prefix as-is", () => {
    const row = renderSingleJob({
      jobId: "pipeline-loading",
      type: "compute:full_pipeline",
      message: "Loading",
    });

    expect(row.textContent).toContain("Pipeline");
    expect(row.textContent).toContain("Loading");
  });
});
