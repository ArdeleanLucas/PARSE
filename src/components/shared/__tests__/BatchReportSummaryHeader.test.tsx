// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BatchReportSummaryHeader } from "../BatchReportSummaryHeader";

describe("BatchReportSummaryHeader", () => {
  afterEach(() => {
    cleanup();
  });
  it("renders the summary chips with the provided totals", () => {
    render(
      <BatchReportSummaryHeader
        totals={{ ok: 3, skipped: 2, empty: 1, errored: 4 }}
        outcomesCount={5}
        allClean={false}
      />,
    );

    expect(screen.getByTestId("batch-report-chip-ok").textContent).toMatch(/3 ok/);
    expect(screen.getByTestId("batch-report-chip-skipped").textContent).toMatch(
      /2 skipped/,
    );
    expect(screen.getByTestId("batch-report-chip-empty").textContent).toMatch(
      /1 empty/,
    );
    expect(screen.getByTestId("batch-report-chip-errored").textContent).toMatch(
      /4 errored/,
    );
  });

  it("shows the all-clean banner when every speaker processed cleanly", () => {
    render(
      <BatchReportSummaryHeader
        totals={{ ok: 8, skipped: 0, empty: 0, errored: 0 }}
        outcomesCount={2}
        allClean
      />,
    );

    expect(screen.getByTestId("batch-report-all-clean").textContent).toMatch(
      /All 2 speakers processed cleanly/,
    );
    expect(screen.queryByTestId("batch-report-chip-empty")).toBeNull();
  });

  it("uses the singular speaker label for a one-speaker clean batch", () => {
    render(
      <BatchReportSummaryHeader
        totals={{ ok: 4, skipped: 0, empty: 0, errored: 0 }}
        outcomesCount={1}
        allClean
      />,
    );

    expect(screen.getByTestId("batch-report-all-clean").textContent).toMatch(
      /All 1 speaker processed cleanly/,
    );
  });
});
