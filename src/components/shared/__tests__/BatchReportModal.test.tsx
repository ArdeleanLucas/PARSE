// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BatchReportModal,
  type BatchSpeakerOutcome,
  type PipelineStepId,
} from "../BatchReportModal";
import type { PipelineRunResult } from "../../../api/client";

function makeResult(
  speaker: string,
  results: PipelineRunResult["results"],
): PipelineRunResult {
  const summary = { ok: 0, skipped: 0, error: 0 };
  for (const key of Object.keys(results) as (keyof PipelineRunResult["results"])[]) {
    const cell = results[key];
    if (!cell) continue;
    if (cell.status === "ok") summary.ok += 1;
    else if (cell.status === "skipped") summary.skipped += 1;
    else if (cell.status === "error") summary.error += 1;
  }
  return {
    speaker,
    steps_run: Object.keys(results),
    results,
    summary,
  };
}

describe("BatchReportModal", () => {
  afterEach(() => {
    cleanup();
  });

  const DEFAULT_STEPS: PipelineStepId[] = ["normalize", "stt", "ortho", "ipa"];

  it("Test A: renders one row per outcome and one col per step", () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          normalize: { status: "ok" },
          stt: { status: "ok", segments: 10 },
        }),
      },
      {
        speaker: "Beta02",
        status: "complete",
        error: null,
        result: makeResult("Beta02", {
          normalize: { status: "ok" },
          stt: { status: "ok", segments: 5 },
        }),
      },
    ];

    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={["normalize", "stt"]}
      />,
    );

    const table = screen.getByTestId("batch-report-table");
    const rows = table.querySelectorAll("tbody > tr");
    expect(rows.length).toBe(2);

    // Header has: speaker + 2 step cols + speaker-status = 4 th
    const headerCells = table.querySelectorAll("thead th");
    expect(headerCells.length).toBe(4);

    // Each body row has 4 td cells.
    const firstRowCells = rows[0].querySelectorAll("td");
    expect(firstRowCells.length).toBe(4);
  });

  it("Test B: ok cell shows compact detail (segment count)", () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          stt: { status: "ok", segments: 142 },
        }),
      },
    ];
    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={["stt"]}
      />,
    );
    const row = screen.getByTestId("batch-report-row-Alpha01");
    expect(row.textContent).toMatch(/142/);
  });

  it("Test C: error cell shows truncated message + Details toggle", () => {
    const longError =
      "ConnectionResetError: connection reset by peer while streaming audio chunk 12 of 47 — retry exhausted after 3 attempts";
    const traceback = [
      "Traceback (most recent call last):",
      '  File "pipeline.py", line 42, in run_stt',
      "    resp = openai.audio.transcribe(...)",
      'ConnectionResetError: connection reset by peer',
    ].join("\n");

    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          stt: {
            status: "error",
            error: longError,
            traceback,
          },
        }),
      },
    ];

    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={["stt"]}
      />,
    );

    const row = screen.getByTestId("batch-report-row-Alpha01");
    // Truncated form visible — contains a leading chunk but not the tail.
    expect(row.textContent).toMatch(/ConnectionResetError/);
    // Full traceback should NOT be visible yet.
    expect(row.textContent).not.toMatch(/retry exhausted after 3 attempts/);

    // Click Details → traceback expands.
    const detailsButton = screen.getByRole("button", { name: /details/i });
    act(() => {
      fireEvent.click(detailsButton);
    });

    const region = screen.getByRole("region", {
      name: /Traceback for Alpha01 stt/,
    });
    expect(region.textContent).toMatch(/retry exhausted after 3 attempts/);
    expect(region.textContent).toMatch(/pipeline\.py/);

    // Click again → collapsed.
    act(() => {
      fireEvent.click(detailsButton);
    });
    expect(
      screen.queryByRole("region", { name: /Traceback for Alpha01 stt/ }),
    ).toBeNull();
  });

  it("Test D: skipped cell shows reason", () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          ortho: {
            status: "skipped",
            reason: "already done; pass overwrite=true to rerun",
          },
        }),
      },
    ];
    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={["ortho"]}
      />,
    );
    const row = screen.getByTestId("batch-report-row-Alpha01");
    expect(row.textContent).toMatch(/already done/);
  });

  it("Test E: summary chips count across all cells", () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          normalize: { status: "ok" },
          stt: { status: "ok", segments: 1 },
          ortho: { status: "skipped", reason: "already done" },
        }),
      },
      {
        speaker: "Beta02",
        status: "complete",
        error: null,
        result: makeResult("Beta02", {
          normalize: { status: "ok" },
          stt: { status: "skipped", reason: "no audio" },
          ortho: { status: "error", error: "boom" },
        }),
      },
    ];
    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={DEFAULT_STEPS}
      />,
    );

    expect(screen.getByTestId("batch-report-chip-ok").textContent).toMatch(
      /3 ok/,
    );
    expect(
      screen.getByTestId("batch-report-chip-skipped").textContent,
    ).toMatch(/2 skipped/);
    expect(
      screen.getByTestId("batch-report-chip-errored").textContent,
    ).toMatch(/1 errored/);
  });

  it("Test F: Rerun failed button calls onRerunFailed with failed speakers only", () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          stt: { status: "error", error: "boom" },
        }),
      },
      {
        speaker: "Beta02",
        status: "complete",
        error: null,
        result: makeResult("Beta02", {
          stt: { status: "ok", segments: 1 },
        }),
      },
      {
        speaker: "Gamma03",
        status: "error",
        error: "network down",
        result: null,
      },
    ];
    const onRerunFailed = vi.fn();

    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={["stt"]}
        onRerunFailed={onRerunFailed}
      />,
    );

    const button = screen.getByTestId(
      "batch-report-rerun-failed",
    ) as HTMLButtonElement;
    expect(button.textContent).toMatch(/\(2\)/);
    expect(button.disabled).toBe(false);

    act(() => {
      fireEvent.click(button);
    });

    expect(onRerunFailed).toHaveBeenCalledTimes(1);
    expect(onRerunFailed).toHaveBeenCalledWith(["Alpha01", "Gamma03"]);
  });

  it("Test G: Download report produces a Blob with expected JSON", async () => {
    const outcomes: BatchSpeakerOutcome[] = [
      {
        speaker: "Alpha01",
        status: "complete",
        error: null,
        result: makeResult("Alpha01", {
          stt: { status: "ok", segments: 7 },
        }),
      },
    ];

    const blobs: Blob[] = [];
    // jsdom doesn't ship URL.createObjectURL by default — install a stub first
    // so we can spy on it.
    const originalCreate = (URL as unknown as { createObjectURL?: unknown })
      .createObjectURL;
    const originalRevoke = (URL as unknown as { revokeObjectURL?: unknown })
      .revokeObjectURL;
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL =
      () => "blob:mock-url";
    (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL =
      () => {};
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockImplementation((b: Blob | MediaSource) => {
        if (b instanceof Blob) blobs.push(b);
        return "blob:mock-url";
      });
    const revokeObjectURL = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => {});

    // Stub out the anchor-click to avoid jsdom navigation weirdness.
    const realCreateElement = document.createElement.bind(document);
    const anchorClick = vi.fn();
    const createElement = vi
      .spyOn(document, "createElement")
      .mockImplementation((tag: string) => {
        const el = realCreateElement(tag) as HTMLElement;
        if (tag === "a") {
          (el as HTMLAnchorElement).click = anchorClick;
        }
        return el;
      });

    render(
      <BatchReportModal
        open
        onClose={() => {}}
        outcomes={outcomes}
        stepsRun={["stt"]}
      />,
    );

    act(() => {
      fireEvent.click(screen.getByTestId("batch-report-download"));
    });

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(blobs.length).toBe(1);

    // jsdom's Blob lacks .text() — read via FileReader instead.
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(blobs[0]);
    });
    const parsed = JSON.parse(text);
    expect(parsed).toHaveProperty("outcomes");
    expect(Array.isArray(parsed.outcomes)).toBe(true);
    expect(parsed.outcomes[0].speaker).toBe("Alpha01");

    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
    createElement.mockRestore();
    if (originalCreate === undefined) {
      delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
    } else {
      (URL as unknown as { createObjectURL: unknown }).createObjectURL =
        originalCreate;
    }
    if (originalRevoke === undefined) {
      delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
    } else {
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL =
        originalRevoke;
    }
  });
});
