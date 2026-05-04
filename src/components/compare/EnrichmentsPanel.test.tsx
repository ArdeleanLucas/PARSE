// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

let mockData: Record<string, unknown> = {};
let mockLoading = false;
const mockLoad = vi.fn(async () => {});
const mockSave = vi.fn(async () => {});

const mockExportLingPyTSV = vi.fn(async () => {});
const mockComputeStart = vi.fn(async () => {});
let mockComputeState: { status: "idle" | "running" | "complete" | "error"; progress: number; error: string | null } = {
  status: "idle",
  progress: 0,
  error: null,
};

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (state: {
    data: Record<string, unknown>;
    loading: boolean;
    load: () => Promise<void>;
    save: (patch: Record<string, unknown>) => Promise<void>;
  }) => unknown) =>
    selector({
      data: mockData,
      loading: mockLoading,
      load: mockLoad,
      save: mockSave,
    }),
}));

vi.mock("../../hooks/useExport", () => ({
  useExport: () => ({
    exportLingPyTSV: mockExportLingPyTSV,
    exportNEXUS: vi.fn(),
    exportCSV: vi.fn(),
  }),
}));

vi.mock("../../hooks/useComputeJob", () => ({
  useComputeJob: () => ({
    start: mockComputeStart,
    state: mockComputeState,
  }),
}));

import { EnrichmentsPanel } from "./EnrichmentsPanel";

beforeEach(() => {
  mockData = {};
  mockLoading = false;
  mockLoad.mockClear();
  mockSave.mockClear();
  mockExportLingPyTSV.mockClear();
  mockComputeStart.mockClear();
  mockComputeState = { status: "idle", progress: 0, error: null };
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

  it("Export LingPy calls useExport hook", async () => {
    mockData = {
      "42": {
        cognate_sets: { A: ["spk1"] },
      },
    };

    render(<EnrichmentsPanel activeConcept="42" />);
    fireEvent.click(screen.getByText("Export LingPy TSV"));

    await vi.waitFor(() => {
      expect(mockExportLingPyTSV).toHaveBeenCalledOnce();
    });
  });
});
