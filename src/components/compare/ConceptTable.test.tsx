// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, Tag } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockConfig: Record<string, unknown> | null = null;
let mockRecords: Record<string, AnnotationRecord> = {};
let mockActiveConcept: string | null = null;
let mockSelectedSpeakers: string[] = [];
let mockEnrichmentData: Record<string, unknown> = {};
let mockTags: Tag[] = [];
const mockSetActiveConcept = vi.fn();

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
      setActiveConcept: mockSetActiveConcept,
    }),
}));

vi.mock("../../stores/enrichmentStore", () => ({
  useEnrichmentStore: (selector: (s: unknown) => unknown) =>
    selector({ data: mockEnrichmentData }),
}));

vi.mock("../../stores/tagStore", () => ({
  useTagStore: (selector: (s: unknown) => unknown) =>
    selector({
      tags: mockTags,
      getTagsForConcept: (conceptId: string) =>
        mockTags.filter((t) => t.concepts.includes(conceptId)),
      getTagsForLexeme: (speaker: string, conceptId: string) => {
        const key = `${speaker}::${conceptId}`;
        return mockTags.filter((t) => (t.lexemeTargets ?? []).includes(key));
      },
      tagLexeme: vi.fn(),
      untagLexeme: vi.fn(),
      addTag: vi.fn(),
    }),
}));

import { ConceptTable } from "./ConceptTable";

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
  mockConfig = null;
  mockRecords = {};
  mockActiveConcept = null;
  mockSelectedSpeakers = [];
  mockEnrichmentData = {};
  mockTags = [];
  mockSetActiveConcept.mockClear();
});

afterEach(cleanup);

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("ConceptTable", () => {
  it("shows 'No concepts loaded' when config has no concepts", () => {
    mockConfig = { speakers: ["Sp1"] };
    render(<ConceptTable />);
    expect(screen.getByText("No concepts loaded.")).toBeTruthy();
  });

  it("renders concept rows", () => {
    mockConfig = { speakers: ["Sp1"], concepts: ["water", "fire"] };
    mockRecords = { Sp1: makeRecord("Sp1", []) };

    render(<ConceptTable />);
    expect(screen.getByText(/water/)).toBeTruthy();
    expect(screen.getByText(/fire/)).toBeTruthy();
  });

  it("renders speaker columns from config", () => {
    mockConfig = { speakers: ["Fail01", "Kalh01"], concepts: ["water"] };
    mockRecords = {};

    render(<ConceptTable />);
    expect(screen.getByText("Fail01")).toBeTruthy();
    expect(screen.getByText("Kalh01")).toBeTruthy();
  });

  it("shows 'No form' when speaker has no annotation for concept", () => {
    mockConfig = { speakers: ["Sp1"], concepts: ["water"] };
    mockRecords = { Sp1: makeRecord("Sp1", []) };

    render(<ConceptTable />);
    expect(screen.getByText("No form")).toBeTruthy();
  });

  it("clicking a row calls setActiveConcept with conceptId", () => {
    mockConfig = { speakers: ["Sp1"], concepts: ["water", "fire"] };
    mockRecords = {};

    render(<ConceptTable />);
    const row = screen.getByTestId("concept-row-water");
    fireEvent.click(row);
    expect(mockSetActiveConcept).toHaveBeenCalledWith("water");
  });

  it("shows cognate badge when enrichmentData has group for concept+speaker", () => {
    mockConfig = { speakers: ["Sp1"], concepts: ["water"] };
    mockRecords = {
      Sp1: makeRecord("Sp1", [
        { id: "water", ipa: "aw", ortho: "awu", start: 0, end: 1 },
      ]),
    };
    mockEnrichmentData = {
      cognate_sets: {
        water: { A: ["Sp1"] },
      },
    };

    render(<ConceptTable />);
    const badge = screen.getByTestId("cognate-badge-water-Sp1");
    expect(badge.textContent).toBe("A");
  });
});
