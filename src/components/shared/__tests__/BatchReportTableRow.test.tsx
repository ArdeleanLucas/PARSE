// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BatchReportTableRow } from "../BatchReportTableRow";
import type { BatchSpeakerOutcome, PipelineStepId } from "../BatchReportModal";

function RowHarness({
  outcome,
  stepsRun,
}: {
  outcome: BatchSpeakerOutcome;
  stepsRun: PipelineStepId[];
}) {
  const [openCells, setOpenCells] = useState<Set<string>>(new Set());
  const [openBanner, setOpenBanner] = useState(false);

  return (
    <table>
      <tbody>
        <BatchReportTableRow
          outcome={outcome}
          stepsRun={stepsRun}
          columnCount={stepsRun.length + 2}
          isCellOpen={(step) => openCells.has(`${outcome.speaker}:${step}`)}
          onToggleCell={(step) => {
            setOpenCells((prev) => {
              const next = new Set(prev);
              const key = `${outcome.speaker}:${step}`;
              if (next.has(key)) next.delete(key);
              else next.add(key);
              return next;
            });
          }}
          isBannerOpen={openBanner}
          onToggleBanner={() => setOpenBanner((prev) => !prev)}
        />
      </tbody>
    </table>
  );
}

describe("BatchReportTableRow", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders one speaker row with per-step cells and status", () => {
    const outcome: BatchSpeakerOutcome = {
      speaker: "Alpha01",
      status: "complete",
      error: null,
      result: {
        speaker: "Alpha01",
        steps_run: ["normalize", "stt", "ortho"],
        results: {
          normalize: { status: "ok" },
          stt: { status: "ok", segments: 17 },
          ortho: { status: "skipped", reason: "already populated" },
        },
        summary: { ok: 2, skipped: 1, error: 0 },
      },
    };

    render(<RowHarness outcome={outcome} stepsRun={["normalize", "stt", "ortho"]} />);

    const row = screen.getByTestId("batch-report-row-Alpha01");
    expect(row.textContent).toMatch(/Alpha01/);
    expect(row.textContent).toMatch(/OK/);
    expect(row.textContent).toMatch(/17 segs/);
    expect(row.textContent).toMatch(/Skipped/);
    expect(row.textContent).toMatch(/already populated/);
    expect(row.textContent).toMatch(/complete/);
  });

  it("expands error and empty-step details through the extracted row component", () => {
    const outcome: BatchSpeakerOutcome = {
      speaker: "Fail02",
      status: "complete",
      error: null,
      result: {
        speaker: "Fail02",
        steps_run: ["stt", "ortho"],
        results: {
          stt: {
            status: "error",
            error: "ConnectionResetError: connection reset by peer while streaming audio chunk 12 of 47 — retry exhausted after 3 attempts",
            traceback: "Traceback (most recent call last):\n  File 'pipeline.py', line 42, in run_stt",
          },
          ortho: {
            status: "ok",
            filled: 0,
            total: 38,
            skip_breakdown: { exception: 38 },
            exception_samples: ["torchcodec decoder failed on interval 17"],
          },
        },
        summary: { ok: 0, skipped: 0, error: 1 },
      },
    };

    render(<RowHarness outcome={outcome} stepsRun={["stt", "ortho"]} />);

    act(() => {
      fireEvent.click(screen.getAllByRole("button", { name: /details|why/i })[0]);
    });
    expect(screen.getByRole("region", { name: /Traceback for Fail02 stt/ }).textContent).toMatch(/pipeline\.py/);

    act(() => {
      fireEvent.click(screen.getAllByRole("button", { name: /details|why/i })[1]);
    });
    expect(screen.getByRole("region", { name: /Empty-step details for Fail02 ortho/ }).textContent).toMatch(/exception/);
    expect(screen.getByRole("region", { name: /Empty-step details for Fail02 ortho/ }).textContent).toMatch(/torchcodec/);
  });

  it("renders and expands the whole-speaker error banner", () => {
    const outcome: BatchSpeakerOutcome = {
      speaker: "Gamma03",
      status: "error",
      error: "Could not reach the PARSE API for POST /api/compute/full_pipeline/status. Traceback: poll loop disconnected after backend job creation.",
      errorPhase: "poll",
      jobId: "job-gamma",
      result: null,
    };

    render(<RowHarness outcome={outcome} stepsRun={["normalize", "stt", "ortho"]} />);

    expect(screen.getByText(/Lost contact after start/i)).toBeTruthy();
    expect(screen.getByText(/job-gamma/)).toBeTruthy();

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /details/i }));
    });

    expect(screen.getByRole("region", { name: /Traceback for Gamma03 speaker/ }).textContent).toMatch(/poll loop disconnected/);
  });
});
