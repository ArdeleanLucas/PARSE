// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { Tag } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockData: Record<string, unknown> = {};
let mockLoading = false;
const mockLoad = vi.fn(async () => {});
const mockSave = vi.fn(async () => {});
let mockTags: Tag[] = [];
const mockGetTagsForConcept = vi.fn((): Tag[] => mockTags);

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (s: unknown) => unknown) =>
    selector({
      data: mockData,
      loading: mockLoading,
      load: mockLoad,
      save: mockSave,
    }),
}));

vi.mock("../../stores/tagStore", () => ({
  useTagStore: (selector: (s: unknown) => unknown) =>
    selector({
      tags: mockTags,
      getTagsForConcept: mockGetTagsForConcept,
    }),
}));

import { EnrichmentsPanel } from "./EnrichmentsPanel";

beforeEach(() => {
  mockData = {};
  mockLoading = false;
  mockLoad.mockClear();
  mockSave.mockClear();
  mockTags = [];
  mockGetTagsForConcept.mockReset().mockReturnValue([]);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("EnrichmentsPanel", () => {
  it("shows placeholder when activeConcept is null", () => {
    render(<EnrichmentsPanel activeConcept={null} />);
    expect(screen.getByTestId("enrichments-placeholder")).toBeTruthy();
    expect(screen.getByText("Select a concept")).toBeTruthy();
  });

  it("shows Spinner while loading", () => {
    mockLoading = true;
    render(<EnrichmentsPanel activeConcept="42" />);
    expect(screen.getByTestId("enrichments-loading")).toBeTruthy();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("renders cognate sets when data present", () => {
    mockData = {
      "42": {
        cognate_sets: {
          A: ["spk1", "spk2"],
          B: ["spk3"],
        },
        ipa_computed: { spk1: "wa" },
      },
    };
    render(<EnrichmentsPanel activeConcept="42" />);
    expect(screen.getByTestId("cognate-sets")).toBeTruthy();
    expect(screen.getByText(/spk1, spk2/)).toBeTruthy();
    expect(screen.getByText(/spk3/)).toBeTruthy();
  });

  it("Verify Cognates calls save with correct patch", () => {
    mockData = {
      "42": {
        cognate_sets: {
          A: ["spk1"],
        },
        manual_overrides: {},
      },
    };
    render(<EnrichmentsPanel activeConcept="42" />);
    fireEvent.click(screen.getByText("Verify Cognates"));
    expect(mockSave).toHaveBeenCalledWith({
      manual_overrides: {
        cognate_sets: { "42": { A: ["spk1"] } },
      },
    });
  });

  it("Export LingPy triggers fetch", async () => {
    mockData = {
      "42": {
        cognate_sets: { A: ["spk1"] },
      },
    };

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("col1\tcol2\nval1\tval2", {
        status: 200,
        headers: { "Content-Type": "text/tab-separated-values" },
      })
    );

    render(<EnrichmentsPanel activeConcept="42" />);
    fireEvent.click(screen.getByText("Export LingPy TSV"));

    // Wait for async
    await vi.waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith("/api/export/lingpy");
    });
  });
});
