// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockGetReport = vi.fn();

vi.mock("../../../api/client", () => ({
  getClefSourcesReport: () => mockGetReport(),
}));

import { ClefSourcesReportModal } from "../ClefSourcesReportModal";
import type { ClefSourcesReport } from "../../../api/types";

const baseCitations = {
  asjp: {
    label: "ASJP",
    type: "dataset" as const,
    authors: "Wichmann, S., Holman, E. W., & Brown, C. H. (eds.)",
    year: 2022,
    title: "The ASJP Database (version 20)",
    url: "https://asjp.clld.org",
    license: "CC-BY-4.0",
    citation:
      "Wichmann, S., Holman, E. W., & Brown, C. H. (eds.). 2022. The ASJP Database (version 20).",
    bibtex:
      "@misc{asjp2022,\n  title = {{The ASJP Database (version 20)}},\n  year = {2022}\n}",
  },
  wikidata: {
    label: "Wikidata",
    type: "dataset" as const,
    authors: "Vrandečić, D. & Krötzsch, M.",
    year: 2014,
    title: "Wikidata: a free collaborative knowledgebase",
    doi: "10.1145/2629489",
    url: "https://www.wikidata.org",
    license: "CC0-1.0",
    citation:
      "Vrandečić, D. & Krötzsch, M. 2014. Wikidata: a free collaborative knowledgebase.",
    bibtex: "@article{wikidata2014, title={Wikidata}, year={2014}}",
  },
  grokipedia: {
    label: "Grokipedia (LLM-generated)",
    type: "ai" as const,
    authors: null,
    year: null,
    title: "LLM-generated reference forms",
    note: "NOT CITABLE AS A PRIMARY SOURCE. Verify each form before using.",
    citation: "Grokipedia provider: LLM-generated. Not citable as primary.",
    bibtex: "",
  },
  unknown: {
    label: "Unattributed (legacy)",
    type: "sentinel" as const,
    authors: null,
    year: null,
    title: "Pre-provenance bare-string entry",
    note: "Re-run CLEF populate with overwrite=true to re-attribute.",
    citation: "Unattributed legacy entry: provider not recorded.",
    bibtex: "",
  },
};

function makeReport(overrides: Partial<ClefSourcesReport> = {}): ClefSourcesReport {
  return {
    generated_at: "2026-04-25T16:00:00Z",
    providers: [
      { id: "asjp", total_forms: 12 },
      { id: "wikidata", total_forms: 3 },
      { id: "grokipedia", total_forms: 1 },
    ],
    languages: [
      {
        code: "ar",
        name: "Arabic",
        family: "Semitic",
        script: "Arab",
        total_forms: 16,
        concepts_covered: 16,
        concepts_total: 20,
        per_provider: { asjp: 12, wikidata: 3, grokipedia: 1 },
        forms: [
          { concept_en: "water", form: "ماء", sources: ["wikidata"] },
          { concept_en: "fire", form: "naːr", sources: ["asjp"] },
        ],
      },
    ],
    concepts_total: 20,
    citations: baseCitations,
    citation_order: ["asjp", "wikidata", "grokipedia", "unknown"],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  mockGetReport.mockReset();
});

describe("ClefSourcesReportModal — academic citations section", () => {
  it("renders one citation block per provider that contributed forms", async () => {
    mockGetReport.mockResolvedValueOnce(makeReport());
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-citations"));

    expect(screen.getByTestId("sources-report-citation-asjp")).toBeTruthy();
    expect(screen.getByTestId("sources-report-citation-wikidata")).toBeTruthy();
    expect(screen.getByTestId("sources-report-citation-grokipedia")).toBeTruthy();
    // ``unknown`` is in citation_order but not in providers -- shouldn't render
    expect(screen.queryByTestId("sources-report-citation-unknown")).toBeNull();
  });

  it("shows full citation text + license + DOI/URL links for bibliographic providers", async () => {
    mockGetReport.mockResolvedValueOnce(makeReport());
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-citation-wikidata"));
    const block = screen.getByTestId("sources-report-citation-wikidata");

    expect(block.textContent).toContain("Vrandečić");
    expect(block.textContent).toContain("Wikidata");
    expect(block.textContent).toContain("CC0-1.0");

    const doiLink = block.querySelector('a[href="https://doi.org/10.1145/2629489"]');
    expect(doiLink).toBeTruthy();
    const urlLink = block.querySelector('a[href="https://www.wikidata.org"]');
    expect(urlLink).toBeTruthy();
  });

  it("flags AI-typed entries with their non-citable warning note", async () => {
    mockGetReport.mockResolvedValueOnce(makeReport());
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-citation-grokipedia"));
    const block = screen.getByTestId("sources-report-citation-grokipedia");

    expect(block.textContent).toContain("NOT CITABLE AS A PRIMARY SOURCE");
    // No BibTeX button for AI rows -- their bibtex is intentionally empty.
    expect(screen.queryByTestId("sources-report-copy-bibtex-grokipedia")).toBeNull();
  });

  it("hides the citations section entirely when no providers contributed", async () => {
    mockGetReport.mockResolvedValueOnce(
      makeReport({
        providers: [],
        languages: [
          {
            code: "ar",
            name: "Arabic",
            family: null,
            total_forms: 0,
            concepts_covered: 0,
            concepts_total: 20,
            per_provider: {},
            forms: [],
          },
        ],
      }),
    );
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    // Wait for the modal body to settle on a non-empty state.
    await waitFor(() => screen.getByText(/No reference forms populated yet|No providers recorded/i));
    expect(screen.queryByTestId("sources-report-citations")).toBeNull();
  });
});

describe("ClefSourcesReportModal — copy + export actions", () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
      writable: true,
    });
  });

  it("Copy citation writes the citation text to the clipboard", async () => {
    mockGetReport.mockResolvedValueOnce(makeReport());
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-copy-cite-asjp"));
    fireEvent.click(screen.getByTestId("sources-report-copy-cite-asjp"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(baseCitations.asjp.citation);
  });

  it("Copy BibTeX writes the BibTeX block to the clipboard", async () => {
    mockGetReport.mockResolvedValueOnce(makeReport());
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-copy-bibtex-wikidata"));
    fireEvent.click(screen.getByTestId("sources-report-copy-bibtex-wikidata"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const arg = writeText.mock.calls[0][0] as string;
    expect(arg).toContain("@article{wikidata2014");
  });

  it("Export BibTeX is shown only when at least one provider has a non-empty bibtex", async () => {
    mockGetReport.mockResolvedValueOnce(makeReport());
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-export-bibtex"));
    expect(screen.getByTestId("sources-report-export-bibtex")).toBeTruthy();
  });

  it("Export BibTeX is hidden when only non-bibliographic providers contributed", async () => {
    mockGetReport.mockResolvedValueOnce(
      makeReport({
        providers: [{ id: "grokipedia", total_forms: 1 }],
        languages: [
          {
            code: "ar",
            name: "Arabic",
            family: null,
            total_forms: 1,
            concepts_covered: 1,
            concepts_total: 20,
            per_provider: { grokipedia: 1 },
            forms: [{ concept_en: "fire", form: "naːr", sources: ["grokipedia"] }],
          },
        ],
      }),
    );
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-citations"));
    expect(screen.queryByTestId("sources-report-export-bibtex")).toBeNull();
  });
});

describe("ClefSourcesReportModal — provider chip styling reflects citation type", () => {
  it("AI provider chips in the per-form table render in the rose accent", async () => {
    mockGetReport.mockResolvedValueOnce(
      makeReport({
        languages: [
          {
            code: "ar",
            name: "Arabic",
            family: null,
            total_forms: 1,
            concepts_covered: 1,
            concepts_total: 20,
            per_provider: { grokipedia: 1 },
            forms: [{ concept_en: "fire", form: "naːr", sources: ["grokipedia"] }],
          },
        ],
        providers: [{ id: "grokipedia", total_forms: 1 }],
      }),
    );
    render(<ClefSourcesReportModal open onClose={() => {}} />);

    await waitFor(() => screen.getByTestId("sources-report-form-row-ar-0"));
    const row = screen.getByTestId("sources-report-form-row-ar-0");
    const chip = Array.from(row.querySelectorAll("span")).find((el) =>
      el.className.includes("rose"),
    );
    expect(chip, "expected an AI-tinted chip in the form row").toBeTruthy();
    expect(chip!.textContent).toContain("Grokipedia");
  });
});
