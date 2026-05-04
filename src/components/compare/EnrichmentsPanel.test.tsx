// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, Tag } from "../../api/types";

let mockData: Record<string, unknown> = {};
let mockLoading = false;
let mockRecords: Record<string, AnnotationRecord> = {};
let mockTags: Tag[] = [];
let mockSelectedSpeakers: string[] = [];
let mockConfigSpeakers: string[] = [];
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

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) => selector({ records: mockRecords }),
}));

vi.mock("../../stores/tagStore", () => ({
  useTagStore: (selector: (state: unknown) => unknown) => selector({ tags: mockTags }),
}));

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (state: unknown) => unknown) => selector({ selectedSpeakers: mockSelectedSpeakers }),
}));

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (selector: (state: unknown) => unknown) => selector({ config: { speakers: mockConfigSpeakers } }),
}));

import { EnrichmentsPanel } from "./EnrichmentsPanel";

function makeRecord(speaker: string, conceptTags: Record<string, string[]> = {}): AnnotationRecord {
  return {
    speaker,
    source_wav: `${speaker}.wav`,
    source_audio: `${speaker}.wav`,
    tiers: { concept: { name: "concept", display_order: 0, intervals: [] } },
    concept_tags: conceptTags,
  };
}

beforeEach(() => {
  mockData = {};
  mockLoading = false;
  mockLoad.mockClear();
  mockSave.mockClear();
  mockExportLingPyTSV.mockClear();
  mockComputeStart.mockClear();
  mockComputeState = { status: "idle", progress: 0, error: null };
  mockSelectedSpeakers = ["S1"];
  mockConfigSpeakers = ["S1", "S2"];
  mockTags = [
    { id: "review-needed", label: "Review needed", color: "#f59e0b" },
    { id: "confirmed", label: "Confirmed", color: "#10b981" },
  ];
  mockRecords = {
    S1: makeRecord("S1", { "42": ["review-needed"] }),
    S2: makeRecord("S2", { "42": ["confirmed"] }),
  };
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



  it("renders tags from selected speaker annotation membership", () => {
    mockData = {
      "42": {
        cognate_sets: { A: ["S1"] },
      },
    };

    render(<EnrichmentsPanel activeConcept="42" />);

    expect(screen.getByText("Review needed")).toBeTruthy();
    expect(screen.queryByText("Confirmed")).toBeNull();
  });

  it("falls back to all configured speakers when resolving concept tags", () => {
    mockSelectedSpeakers = [];
    mockData = {
      "42": {
        cognate_sets: { A: ["S1"] },
      },
    };

    render(<EnrichmentsPanel activeConcept="42" />);

    expect(screen.getByText("Review needed")).toBeTruthy();
    expect(screen.getByText("Confirmed")).toBeTruthy();
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
