// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockActiveConcept: string | null = null;
let mockSelectedSpeakers: string[] = [];
let mockEnrichmentData: Record<string, unknown> = {};
let mockRecords: Record<string, AnnotationRecord> = {};
let mockConfig: Record<string, unknown> | null = null;
const mockSave = vi.fn().mockResolvedValue(undefined);

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: unknown) => unknown) =>
    selector({
      activeConcept: mockActiveConcept,
      selectedSpeakers: mockSelectedSpeakers,
    }),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (s: unknown) => unknown) =>
    selector({
      data: mockEnrichmentData,
      save: mockSave,
    }),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (s: unknown) => unknown) =>
    selector({ records: mockRecords }),
}));

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (selector: (s: unknown) => unknown) =>
    selector({ config: mockConfig }),
}));

import { CognateControls } from "./CognateControls";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function makeRecord(
  speaker: string,
  concepts: { id: string; ipa: string; start: number; end: number }[],
): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 1,
        intervals: concepts.map((c) => ({ start: c.start, end: c.end, text: c.ipa })),
      },
      ortho: { name: "ortho", display_order: 2, intervals: [] },
      concept: {
        name: "concept",
        display_order: 3,
        intervals: concepts.map((c) => ({ start: c.start, end: c.end, text: c.id })),
      },
      speaker: { name: "speaker", display_order: 4, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    source_wav: "",
  };
}

/* ------------------------------------------------------------------ */
/*  Setup / teardown                                                   */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  mockActiveConcept = null;
  mockSelectedSpeakers = [];
  mockEnrichmentData = {};
  mockRecords = {};
  mockConfig = null;
  mockSave.mockClear();
});

afterEach(cleanup);

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("CognateControls", () => {
  it("shows placeholder when activeConcept is null", () => {
    mockActiveConcept = null;
    render(<CognateControls />);
    expect(screen.getByText("Select a concept in the table.")).toBeTruthy();
  });

  it("renders speaker buttons", () => {
    mockActiveConcept = "water";
    mockConfig = { speakers: ["Sp1", "Sp2"] };
    mockRecords = {
      Sp1: makeRecord("Sp1", [{ id: "water", ipa: "aw", start: 0, end: 1 }]),
      Sp2: makeRecord("Sp2", [{ id: "water", ipa: "av", start: 0, end: 1 }]),
    };

    render(<CognateControls />);
    expect(screen.getByTestId("speaker-btn-Sp1")).toBeTruthy();
    expect(screen.getByTestId("speaker-btn-Sp2")).toBeTruthy();
  });

  it("Merge puts all speakers in group A", () => {
    mockActiveConcept = "water";
    mockConfig = { speakers: ["Sp1", "Sp2"] };
    mockRecords = {
      Sp1: makeRecord("Sp1", [{ id: "water", ipa: "aw", start: 0, end: 1 }]),
      Sp2: makeRecord("Sp2", [{ id: "water", ipa: "av", start: 0, end: 1 }]),
    };
    mockEnrichmentData = {
      cognate_sets: { water: { A: ["Sp1"], B: ["Sp2"] } },
    };

    render(<CognateControls />);
    fireEvent.click(screen.getByText("Merge"));

    // After merge both should show group A
    const sp1Btn = screen.getByTestId("speaker-btn-Sp1");
    const sp2Btn = screen.getByTestId("speaker-btn-Sp2");
    expect(sp1Btn.textContent).toContain("A");
    expect(sp2Btn.textContent).toContain("A");
  });

  it("does not report or keep a merged state when save fails", async () => {
    mockActiveConcept = "water";
    mockConfig = { speakers: ["Sp1", "Sp2"] };
    mockRecords = {
      Sp1: makeRecord("Sp1", [{ id: "water", ipa: "aw", start: 0, end: 1 }]),
      Sp2: makeRecord("Sp2", [{ id: "water", ipa: "av", start: 0, end: 1 }]),
    };
    mockEnrichmentData = {
      cognate_sets: { water: { A: ["Sp1"], B: ["Sp2"] } },
    };
    const onGroupsChanged = vi.fn();
    mockSave.mockRejectedValueOnce(new Error("save failed"));

    render(<CognateControls onGroupsChanged={onGroupsChanged} />);
    fireEvent.click(screen.getByText("Merge"));

    await waitFor(() => {
      expect(mockSave).toHaveBeenCalledTimes(1);
      expect(onGroupsChanged).not.toHaveBeenCalled();
      expect(screen.getByTestId("speaker-btn-Sp1").textContent).toContain("A");
      expect(screen.getByTestId("speaker-btn-Sp2").textContent).toContain("B");
    });
  });

  it("split mode toggled by Split button", () => {
    mockActiveConcept = "water";
    mockConfig = { speakers: ["Sp1"] };
    mockRecords = {
      Sp1: makeRecord("Sp1", [{ id: "water", ipa: "aw", start: 0, end: 1 }]),
    };

    render(<CognateControls />);

    // Initially no "Target group:" visible
    expect(screen.queryByText("Target group:")).toBeNull();

    fireEvent.click(screen.getByText("Split"));
    expect(screen.getByText("Target group:")).toBeTruthy();

    // Toggle off
    fireEvent.click(screen.getByText("Split"));
    expect(screen.queryByText("Target group:")).toBeNull();
  });

  it("cycle click advances speaker group A→B", () => {
    mockActiveConcept = "water";
    mockConfig = { speakers: ["Sp1"] };
    mockRecords = {
      Sp1: makeRecord("Sp1", [{ id: "water", ipa: "aw", start: 0, end: 1 }]),
    };
    mockEnrichmentData = {
      cognate_sets: { water: { A: ["Sp1"] } },
    };

    render(<CognateControls />);

    // Enable cycle mode
    fireEvent.click(screen.getByText("Cycle"));

    const btn = screen.getByTestId("speaker-btn-Sp1");
    expect(btn.textContent).toContain("A");

    fireEvent.click(btn);
    expect(btn.textContent).toContain("B");
  });
});
