// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, AnnotationInterval } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockActiveSpeaker: string | null = null;
let mockActiveConcept: string | null = null;
let mockSelectedRegion: { start: number; end: number } | null = null;
let mockRecords: Record<string, AnnotationRecord> = {};
const mockAddInterval = vi.fn();
const mockRemoveInterval = vi.fn();

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (
    selector: (s: { activeSpeaker: string | null; activeConcept: string | null }) => unknown,
  ) => selector({ activeSpeaker: mockActiveSpeaker, activeConcept: mockActiveConcept }),
}));

vi.mock("../../stores/playbackStore", () => ({
  usePlaybackStore: (
    selector: (s: { selectedRegion: { start: number; end: number } | null }) => unknown,
  ) => selector({ selectedRegion: mockSelectedRegion }),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (s: unknown) => unknown) =>
    selector({
      records: mockRecords,
      addInterval: mockAddInterval,
      removeInterval: mockRemoveInterval,
    }),
}));

import { AnnotationPanel } from "./AnnotationPanel";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function makeRecord(speaker: string, ipaIntervals: AnnotationInterval[] = []): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa: { name: "ipa", display_order: 1, intervals: ipaIntervals },
      ortho: { name: "ortho", display_order: 2, intervals: [] },
      concept: { name: "concept", display_order: 3, intervals: [] },
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
  mockActiveSpeaker = null;
  mockActiveConcept = null;
  mockSelectedRegion = null;
  mockRecords = {};
  mockAddInterval.mockClear();
  mockRemoveInterval.mockClear();
});

afterEach(cleanup);

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("AnnotationPanel", () => {
  it('renders "No region selected" when selectedRegion is null', () => {
    mockActiveSpeaker = "spk1";
    mockActiveConcept = "c1";
    render(<AnnotationPanel />);
    expect(screen.getByText("No region selected")).toBeTruthy();
  });

  it("Save button disabled when no region", () => {
    mockActiveSpeaker = "spk1";
    mockActiveConcept = "c1";
    render(<AnnotationPanel />);
    const btn = screen.getByText("Save annotation");
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("Save button enabled when region + ipa text provided", () => {
    mockActiveSpeaker = "spk1";
    mockActiveConcept = "c1";
    mockSelectedRegion = { start: 1.0, end: 2.0 };
    render(<AnnotationPanel />);

    const ipaInput = screen.getByLabelText("IPA");
    fireEvent.change(ipaInput, { target: { value: "test-ipa" } });

    const btn = screen.getByText("Save annotation");
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("clicking Save calls addInterval for each non-empty tier field", () => {
    mockActiveSpeaker = "spk1";
    mockActiveConcept = "c1";
    mockSelectedRegion = { start: 1.234, end: 5.678 };
    const onSaved = vi.fn();
    render(<AnnotationPanel onAnnotationSaved={onSaved} />);

    fireEvent.change(screen.getByLabelText("IPA"), { target: { value: "ipa-val" } });
    fireEvent.change(screen.getByLabelText("Ortho"), { target: { value: "ortho-val" } });
    // concept should be pre-filled with "c1"

    fireEvent.click(screen.getByText("Save annotation"));

    expect(mockAddInterval).toHaveBeenCalledTimes(3);
    expect(mockAddInterval).toHaveBeenCalledWith("spk1", "ipa", {
      start: 1.234,
      end: 5.678,
      text: "ipa-val",
    });
    expect(mockAddInterval).toHaveBeenCalledWith("spk1", "ortho", {
      start: 1.234,
      end: 5.678,
      text: "ortho-val",
    });
    expect(mockAddInterval).toHaveBeenCalledWith("spk1", "concept", {
      start: 1.234,
      end: 5.678,
      text: "c1",
    });

    expect(onSaved).toHaveBeenCalledWith("spk1", "ipa", {
      start: 1.234,
      end: 5.678,
      text: "ipa-val",
    });

    expect(screen.getByText("Saved.")).toBeTruthy();
  });

  it("clicking Delete calls removeInterval with correct index", () => {
    mockActiveSpeaker = "spk1";
    mockActiveConcept = "c1";
    mockRecords = {
      spk1: makeRecord("spk1", [
        { start: 1.0, end: 2.0, text: "first" },
        { start: 3.0, end: 4.0, text: "second" },
      ]),
    };
    render(<AnnotationPanel />);

    const deleteButtons = screen.getAllByText("Delete");
    expect(deleteButtons).toHaveLength(2);

    fireEvent.click(deleteButtons[1]);
    expect(mockRemoveInterval).toHaveBeenCalledWith("spk1", "ipa", 1);
  });

  it("inputs clear and concept pre-fills when activeSpeaker changes", () => {
    mockActiveSpeaker = "spk1";
    mockActiveConcept = "c1";
    mockSelectedRegion = { start: 1.0, end: 2.0 };
    const { rerender } = render(<AnnotationPanel />);

    // Type into IPA
    fireEvent.change(screen.getByLabelText("IPA"), { target: { value: "typed" } });
    expect((screen.getByLabelText("IPA") as HTMLInputElement).value).toBe("typed");

    // Concept should be pre-filled
    expect((screen.getByLabelText("Concept") as HTMLInputElement).value).toBe("c1");

    // Change speaker
    mockActiveSpeaker = "spk2";
    mockActiveConcept = "c2";
    rerender(<AnnotationPanel />);

    expect((screen.getByLabelText("IPA") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Ortho") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Concept") as HTMLInputElement).value).toBe("c2");
  });
});
