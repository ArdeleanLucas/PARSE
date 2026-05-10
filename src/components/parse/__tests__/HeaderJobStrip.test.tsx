// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ActiveJobSnapshot } from "../../../api/contracts/job-observability";
import { HeaderJobStrip, friendlyLabel } from "../HeaderJobStrip";

const baseJob = (overrides: Partial<ActiveJobSnapshot> = {}): ActiveJobSnapshot => ({
  jobId: "job-1",
  type: "compute:lexeme_rerun_ortho",
  status: "running",
  progress: 0.4,
  message: "Working",
  ...overrides,
});

describe("HeaderJobStrip", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("renders an empty wrapper with no rows for an empty job list", () => {
    render(<HeaderJobStrip jobs={[]} />);

    const strip = screen.getByTestId("topbar-job-strip");
    expect(strip).toBeTruthy();
    expect(strip.querySelectorAll('[data-testid^="topbar-job-strip-row-"]')).toHaveLength(0);
  });

  it("renders rows with friendly labels, progress widths, and percent text", () => {
    render(<HeaderJobStrip jobs={[
      baseJob({ jobId: "ipa-job", type: "compute:lexeme_rerun_ipa", progress: 0.25 }),
      baseJob({ jobId: "tag-job", type: "compute:lexemes_rerun_by_tag", progress: 0.75 }),
    ]} />);

    const ipaRow = screen.getByTestId("topbar-job-strip-row-ipa-job");
    expect(within(ipaRow).getByText("Lexeme IPA")).toBeTruthy();
    expect(within(ipaRow).getByText("25%")).toBeTruthy();
    expect((within(ipaRow).getByTestId("topbar-job-progress-ipa-job") as HTMLElement).style.width).toBe("25%");

    const tagRow = screen.getByTestId("topbar-job-strip-row-tag-job");
    expect(within(tagRow).getByText("Tagged rerun")).toBeTruthy();
    expect(within(tagRow).getByText("75%")).toBeTruthy();
  });

  it("renders the pulsing placeholder bar for very early progress", () => {
    render(<HeaderJobStrip jobs={[baseJob({ progress: 0.03 })]} />);

    const placeholder = screen.getByTestId("topbar-job-progress-placeholder-job-1");
    expect(placeholder.className).toContain("animate-pulse");
    expect(placeholder.className).toContain("w-1/3");
  });

  it("renders ETA text when etaMs is positive", () => {
    render(<HeaderJobStrip jobs={[baseJob({ etaMs: 125_000 } as Partial<ActiveJobSnapshot>)]} />);

    const row = screen.getByTestId("topbar-job-strip-row-job-1");
    expect(row.textContent).toContain("~2m 5s left");
  });

  it("calls onCancel with the job id", () => {
    const onCancel = vi.fn().mockResolvedValue(undefined);
    render(<HeaderJobStrip jobs={[baseJob({ jobId: "cancel-me" })]} onCancel={onCancel} />);

    fireEvent.click(screen.getByRole("button", { name: /Cancel cancel-me/i }));

    expect(onCancel).toHaveBeenCalledWith("cancel-me");
  });

  it("auto-dismisses completed jobs after the configured delay", async () => {
    render(<HeaderJobStrip jobs={[baseJob({ status: "complete", progress: 1 })]} autoDismissMs={4000} />);

    expect(screen.getByText("Lexeme ORTH done")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(screen.queryByTestId("topbar-job-strip-row-job-1")).toBeNull();
  });

  it("auto-dismisses errored jobs after the configured delay", async () => {
    render(<HeaderJobStrip jobs={[baseJob({ status: "error", error: "boom" })]} autoDismissMs={4000} />);

    expect(screen.getByText("Lexeme ORTH failed")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(screen.queryByTestId("topbar-job-strip-row-job-1")).toBeNull();
  });

  it("renders cancelled jobs with the amber terminal chip and no Cancel button", () => {
    render(<HeaderJobStrip jobs={[baseJob({ status: "cancelled", progress: 1 })]} />);

    const row = screen.getByTestId("topbar-job-strip-row-job-1");
    expect(row.className).toContain("border-amber-200");
    expect(row.className).toContain("bg-amber-50");
    expect(within(row).getByText("Lexeme ORTH cancelled").className).toContain("text-amber-900");
    expect(screen.queryByRole("button", { name: /Cancel/i })).toBeNull();
    expect(screen.queryByTestId("topbar-job-progress-job-1")).toBeNull();
    expect(screen.queryByTestId("topbar-job-progress-placeholder-job-1")).toBeNull();
  });

  it("auto-dismisses cancelled jobs after the configured delay", async () => {
    render(<HeaderJobStrip jobs={[baseJob({ status: "cancelled", progress: 1 })]} autoDismissMs={4000} />);

    expect(screen.getByText("Lexeme ORTH cancelled")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(screen.queryByTestId("topbar-job-strip-row-job-1")).toBeNull();
  });

  it("treats both 'cancelled' and 'canceled' as the same terminal state", () => {
    render(<HeaderJobStrip jobs={[
      baseJob({ jobId: "cancelled-job", status: "cancelled", progress: 1 }),
      baseJob({ jobId: "canceled-job", status: "canceled", progress: 1 }),
    ]} />);

    expect(within(screen.getByTestId("topbar-job-strip-row-cancelled-job")).getByText("Lexeme ORTH cancelled")).toBeTruthy();
    expect(within(screen.getByTestId("topbar-job-strip-row-canceled-job")).getByText("Lexeme ORTH cancelled")).toBeTruthy();
  });

  it("renders errored jobs with crash-log affordance", () => {
    const onOpenLogs = vi.fn();
    render(<HeaderJobStrip jobs={[baseJob({ status: "error", error: "CUDA exploded while transcribing a very long chunk" })]} onOpenLogs={onOpenLogs} />);

    const row = screen.getByTestId("topbar-job-strip-row-job-1");
    expect(row.className).toContain("border-rose-200");
    expect(within(row).getByText(/CUDA exploded/)).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: /View crash log/i }));
    expect(onOpenLogs).toHaveBeenCalledWith("job-1");
  });

  it("falls back to title-casing the segment after the colon for unknown job types", () => {
    expect(friendlyLabel("compute:future_magic_job")).toBe("Future Magic Job");
  });

  it("sorts most-recently-started jobs first", () => {
    render(<HeaderJobStrip jobs={[
      baseJob({ jobId: "older", type: "compute:ipa", startedTs: 100 } as Partial<ActiveJobSnapshot>),
      baseJob({ jobId: "newer", type: "compute:ortho", startedTs: 200 } as Partial<ActiveJobSnapshot>),
    ]} />);

    const rows = Array.from(screen.getByTestId("topbar-job-strip").querySelectorAll('[data-testid^="topbar-job-strip-row-"]'));
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "topbar-job-strip-row-newer",
      "topbar-job-strip-row-older",
    ]);
  });
});
