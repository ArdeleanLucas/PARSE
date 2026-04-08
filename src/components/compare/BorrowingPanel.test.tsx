// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockConfig: Record<string, unknown> | null = null;
let mockRecords: Record<string, AnnotationRecord> = {};
let mockActiveConcept: string | null = null;
let mockSelectedSpeakers: string[] = [];
let mockEnrichmentData: Record<string, unknown> = {};
const mockSaveEnrichments = vi.fn().mockResolvedValue(undefined);

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (selector: (s: unknown) => unknown) =>
    selector({ config: mockConfig }),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (s: unknown) => unknown) =>
    selector({ records: mockRecords }),
}));

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: unknown) => unknown) =>
    selector({
      activeConcept: mockActiveConcept,
      selectedSpeakers: mockSelectedSpeakers,
    }),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (s: unknown) => unknown) =>
    selector({ data: mockEnrichmentData, save: mockSaveEnrichments }),
}));

import { BorrowingPanel } from "./BorrowingPanel";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function makeRecord(
  speaker: string,
  concepts: { id: string; ipa: string; ortho: string; start: number; end: number }[],
): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 1,
        intervals: concepts.map((c) => ({ start: c.start, end: c.end, text: c.ipa })),
      },
      ortho: {
        name: "ortho",
        display_order: 2,
        intervals: concepts.map((c) => ({ start: c.start, end: c.end, text: c.ortho })),
      },
      concept: {
        name: "concept",
        display_order: 3,
        intervals: concepts.map((c) => ({ start: c.start, end: c.end, text: c.id })),
      },
      speaker: { name: "speaker", display_order: 4, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    source_wav: "test.wav",
  };
}

/* ------------------------------------------------------------------ */
/*  Setup / teardown                                                   */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  mockConfig = { speakers: ["Fail01", "Kalh01"], concepts: ["1", "2"] };
  mockRecords = {
    Fail01: makeRecord("Fail01", [
      { id: "1", ipa: "awu", ortho: "awu", start: 0, end: 1 },
    ]),
    Kalh01: makeRecord("Kalh01", []),
  };
  mockActiveConcept = "1";
  mockSelectedSpeakers = ["Fail01", "Kalh01"];
  mockEnrichmentData = {
    borrowing_flags: {
      "1": { Fail01: "native" },
    },
    similarity: {
      "1": {
        Fail01: { ar: 0.42, tr: 0.12 },
        Kalh01: { ar: 0.55 },
      },
    },
  };
  mockSaveEnrichments.mockClear();

  // Mock fetch for contact languages
  vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    json: () =>
      Promise.resolve([
        { code: "ar", name: "Arabic", family: "Semitic" },
        { code: "tr", name: "Turkish", family: "Turkic" },
      ]),
  } as Response);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("BorrowingPanel", () => {
  it("renders 'Select a concept' when activeConcept is null", () => {
    mockActiveConcept = null;
    render(<BorrowingPanel />);
    expect(screen.getByText("Select a concept")).toBeTruthy();
  });

  it("renders form preview per speaker", async () => {
    render(<BorrowingPanel />);
    // Fail01 has form "awu / awu" — appears in both forms section and adjudication
    expect(screen.getAllByText(/Fail01/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("awu / awu")).toBeTruthy();
    // Kalh01 has no form
    expect(screen.getByText("No form")).toBeTruthy();
  });

  it("radio change updates local decision", () => {
    render(<BorrowingPanel />);
    const radioUncertain = screen.getByTestId("radio-Fail01-uncertain");
    fireEvent.click(radioUncertain);
    expect((radioUncertain as HTMLInputElement).checked).toBe(true);
  });

  it("'borrowed' decision shows source lang select", async () => {
    render(<BorrowingPanel />);
    // Wait for contact languages to load
    await waitFor(() => {
      expect(screen.getByText(/Arabic/)).toBeTruthy();
    });

    const radioBorrowed = screen.getByTestId("radio-Fail01-borrowed");
    fireEvent.click(radioBorrowed);
    expect(screen.getByText("Source language")).toBeTruthy();
  });

  it("'skip' hides source lang; speaker with no form forced to skip", () => {
    render(<BorrowingPanel />);
    // Kalh01 has no form — non-skip radios should be disabled
    const nativeRadio = screen.getByTestId("radio-Kalh01-native") as HTMLInputElement;
    const borrowedRadio = screen.getByTestId("radio-Kalh01-borrowed") as HTMLInputElement;
    const skipRadio = screen.getByTestId("radio-Kalh01-skip") as HTMLInputElement;

    expect(nativeRadio.disabled).toBe(true);
    expect(borrowedRadio.disabled).toBe(true);
    expect(skipRadio.disabled).toBe(false);

    // Fail01 skip should not show source lang
    const failSkip = screen.getByTestId("radio-Fail01-skip");
    fireEvent.click(failSkip);
    expect(screen.queryByText("Source language")).toBeNull();
  });

  it("Save Decisions calls enrichmentStore.save with merged flags", async () => {
    render(<BorrowingPanel />);
    // Make a local decision
    const radioBorrowed = screen.getByTestId("radio-Fail01-borrowed");
    fireEvent.click(radioBorrowed);

    const saveBtn = screen.getByText("Save Decisions");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockSaveEnrichments).toHaveBeenCalledTimes(1);
    });

    const call = mockSaveEnrichments.mock.calls[0][0];
    expect(call.manual_overrides.borrowing_flags["1"].Fail01.decision).toBe("borrowed");
  });
});
