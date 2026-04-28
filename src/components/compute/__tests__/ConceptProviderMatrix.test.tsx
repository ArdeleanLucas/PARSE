// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGetReport = vi.fn();

vi.mock("../../../api/client", () => ({
  getClefSourcesReport: () => mockGetReport(),
}));

import { ClefSourcesReportModal } from "../ClefSourcesReportModal";
import { MatrixCell } from "../clef/ConceptProviderMatrix";
import type { ClefSourcesReport } from "../../../api/types";

function makeReport(): ClefSourcesReport {
  return {
    generated_at: "2026-04-28T09:00:00Z",
    providers: [
      { id: "wikidata", total_forms: 2 },
      { id: "grokipedia", total_forms: 1 },
    ],
    languages: [
      {
        code: "ar",
        name: "Arabic",
        family: "Semitic",
        script: "Arab",
        total_forms: 3,
        concepts_covered: 2,
        concepts_total: 2,
        per_provider: { wikidata: 2, grokipedia: 1 },
        forms: [
          { concept_en: "water", form: "ماء", sources: ["wikidata"] },
          { concept_en: "water", form: "maːʔ", sources: ["grokipedia"] },
          { concept_en: "fire", form: "naːr", sources: ["wikidata"] },
        ],
      },
    ],
    concepts_total: 2,
    citations: {
      wikidata: {
        label: "Wikidata",
        type: "dataset",
        authors: "Vrandečić, D. & Krötzsch, M.",
        year: 2014,
        title: "Wikidata",
        citation: "Wikidata citation",
        bibtex: "@article{wikidata}",
      },
      grokipedia: {
        label: "Grokipedia",
        type: "ai",
        authors: null,
        year: null,
        title: "Grokipedia",
        citation: "Grokipedia citation",
        bibtex: "",
        note: "Verify",
      },
    },
    citation_order: ["wikidata", "grokipedia"],
  };
}

afterEach(() => {
  cleanup();
  mockGetReport.mockReset();
});

describe("MatrixCell", () => {
  it("renders count, blank, and error states", () => {
    const { rerender, container } = render(<MatrixCell count={2} errored={false} onClick={() => {}} />);
    expect(screen.getByRole("button").textContent).toContain("2");

    rerender(<MatrixCell count={0} errored={false} onClick={() => {}} />);
    expect(container.querySelector("[aria-label='No forms']")).not.toBeNull();

    rerender(<MatrixCell count={0} errored onClick={() => {}} />);
    expect(screen.getByRole("button").textContent).toContain("✕");
  });
});

describe("ClefSourcesReportModal matrix", () => {
  beforeEach(() => {
    mockGetReport.mockResolvedValue(makeReport());
  });

  it("renders the concept × provider matrix", async () => {
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("concept-provider-matrix"));
    expect(screen.getByTestId("concept-provider-cell-water-wikidata")).toBeTruthy();
    expect(screen.getByTestId("concept-provider-cell-water-grokipedia")).toBeTruthy();
  });

  it("opens a drill-down drawer when a populated matrix cell is clicked", async () => {
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("concept-provider-matrix"));
    fireEvent.click(screen.getByTestId("concept-provider-cell-water-wikidata"));

    const drawer = await screen.findByTestId("concept-provider-drawer");
    expect(drawer.textContent).toContain("ماء");
    expect(drawer.textContent).toContain("Wikidata citation");
  });
});
