// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, Tag } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockTags: Tag[] = [];
const mockAddTag = vi.fn();
const mockRemoveTag = vi.fn();
const mockUpdateTag = vi.fn();
const mockSetConceptTag = vi.fn();
const mockClearConceptTag = vi.fn();
let mockRecords: Record<string, AnnotationRecord> = {};
let mockSelectedSpeakers: string[] = [];

let mockActiveConcept: string | null = null;

let mockConfig: Record<string, unknown> | null = {
  project_name: "test",
  language_code: "en",
  speakers: ["S1", "S2"],
  audio_dir: "",
  annotations_dir: "",
  concepts: [
    { id: "c1", label: "water" },
    { id: "c2", label: "fire" },
    { id: "c3", label: "earth" },
  ],
};

vi.mock("../../stores/tagStore", () => ({
  useTagStore: (selector: (s: unknown) => unknown) =>
    selector({
      tags: mockTags,
      addTag: mockAddTag,
      removeTag: mockRemoveTag,
      updateTag: mockUpdateTag,
    }),
}));

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: unknown) => unknown) =>
    selector({ activeConcept: mockActiveConcept, selectedSpeakers: mockSelectedSpeakers }),
}));

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (selector: (s: unknown) => unknown) =>
    selector({ config: mockConfig }),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (s: unknown) => unknown) =>
    selector({
      records: mockRecords,
      setConceptTag: mockSetConceptTag,
      clearConceptTag: mockClearConceptTag,
    }),
}));

import { TagManager } from "./TagManager";

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
  mockTags = [
    { id: "t1", label: "Review", color: "#f59e0b" },
    { id: "t2", label: "Confirmed", color: "#10b981" },
  ];
  mockAddTag.mockClear();
  mockRemoveTag.mockClear();
  mockUpdateTag.mockClear();
  mockSetConceptTag.mockClear();
  mockClearConceptTag.mockClear();
  mockSelectedSpeakers = ["S1"];
  mockRecords = {
    S1: makeRecord("S1", { c1: ["t1"] }),
    S2: makeRecord("S2", { c2: ["t1"] }),
  };
});

afterEach(() => {
  cleanup();
});

describe("TagManager", () => {
  it("renders tag list with add form", () => {
    render(<TagManager isOpen={true} onClose={() => {}} />);
    expect(screen.getByText("Review")).toBeTruthy();
    expect(screen.getByText("Confirmed")).toBeTruthy();
    expect(screen.getByTestId("add-tag-form")).toBeTruthy();
    expect(screen.getByPlaceholderText("Tag label")).toBeTruthy();
  });

  it("Add calls addTag with label and color", () => {
    render(<TagManager isOpen={true} onClose={() => {}} />);
    const labelInput = screen.getByPlaceholderText("Tag label");
    fireEvent.change(labelInput, { target: { value: "New Tag" } });
    const addBtn = screen.getByText("Add");
    fireEvent.click(addBtn);
    expect(mockAddTag).toHaveBeenCalledWith("New Tag", "#6b7280");
  });

  it("Delete calls removeTag", () => {
    render(<TagManager isOpen={true} onClose={() => {}} />);
    const deleteBtns = screen.getAllByText("Delete");
    fireEvent.click(deleteBtns[0]);
    expect(mockRemoveTag).toHaveBeenCalledWith("t1");
  });

  it("renders concept chips as vocabulary-only context for the selected tag", () => {
    render(<TagManager isOpen={true} onClose={() => {}} />);

    fireEvent.click(screen.getByTestId("tag-row-t1"));

    expect(screen.getByTestId("concept-chip-c1")).toBeTruthy();
    expect(screen.getByTestId("concept-chip-c2")).toBeTruthy();
  });



  it("toggles selected tag membership for selected speakers", () => {
    render(<TagManager isOpen={true} onClose={() => {}} />);

    fireEvent.click(screen.getByTestId("tag-row-t1"));
    expect(screen.getByTestId("concept-chip-c1").textContent).toContain("water");

    fireEvent.click(screen.getByTestId("concept-chip-c3"));
    expect(mockSetConceptTag).toHaveBeenCalledWith("S1", "c3", "t1");

    fireEvent.click(screen.getByTestId("concept-chip-c1"));
    expect(mockClearConceptTag).toHaveBeenCalledWith("S1", "c1", "t1");
  });

  it("tags and untags all visible concepts across all configured speakers when none are selected", () => {
    mockSelectedSpeakers = [];
    render(<TagManager isOpen={true} onClose={() => {}} />);

    fireEvent.click(screen.getByTestId("tag-row-t1"));
    fireEvent.change(screen.getByTestId("concept-search"), { target: { value: "wat" } });
    fireEvent.click(screen.getByText("Tag all visible"));

    expect(mockSetConceptTag).toHaveBeenCalledWith("S1", "c1", "t1");
    expect(mockSetConceptTag).toHaveBeenCalledWith("S2", "c1", "t1");

    fireEvent.click(screen.getByText("Untag all visible"));
    expect(mockClearConceptTag).toHaveBeenCalledWith("S1", "c1", "t1");
    expect(mockClearConceptTag).toHaveBeenCalledWith("S2", "c1", "t1");
  });

  it("search filters concept chips", () => {
    render(<TagManager isOpen={true} onClose={() => {}} />);

    // Select a tag
    fireEvent.click(screen.getByTestId("tag-row-t1"));

    // All concepts visible
    expect(screen.getByTestId("concept-chip-c1")).toBeTruthy();
    expect(screen.getByTestId("concept-chip-c2")).toBeTruthy();
    expect(screen.getByTestId("concept-chip-c3")).toBeTruthy();

    // Search for "wat"
    const searchInput = screen.getByTestId("concept-search");
    fireEvent.change(searchInput, { target: { value: "wat" } });

    expect(screen.getByTestId("concept-chip-c1")).toBeTruthy(); // water
    expect(screen.queryByTestId("concept-chip-c2")).toBeNull(); // fire - hidden
    expect(screen.queryByTestId("concept-chip-c3")).toBeNull(); // earth - hidden
  });
});
