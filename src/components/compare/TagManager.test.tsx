// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { Tag } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockTags: Tag[] = [];
const mockAddTag = vi.fn();
const mockRemoveTag = vi.fn();
const mockUpdateTag = vi.fn();
const mockTagConcept = vi.fn();
const mockUntagConcept = vi.fn();
const mockGetTagsForConcept = vi.fn((_conceptId: string): Tag[] => []);

let mockActiveConcept: string | null = null;

let mockConfig: Record<string, unknown> | null = {
  project_name: "test",
  language_code: "en",
  speakers: [],
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
      tagConcept: mockTagConcept,
      untagConcept: mockUntagConcept,
      getTagsForConcept: mockGetTagsForConcept,
    }),
}));

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: unknown) => unknown) =>
    selector({ activeConcept: mockActiveConcept }),
}));

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (selector: (s: unknown) => unknown) =>
    selector({ config: mockConfig }),
}));

import { TagManager } from "./TagManager";

beforeEach(() => {
  mockTags = [
    { id: "t1", label: "Review", color: "#f59e0b", concepts: ["c1"] },
    { id: "t2", label: "Confirmed", color: "#10b981", concepts: [] },
  ];
  mockAddTag.mockClear();
  mockRemoveTag.mockClear();
  mockUpdateTag.mockClear();
  mockTagConcept.mockClear();
  mockUntagConcept.mockClear();
  mockGetTagsForConcept.mockReset().mockReturnValue([]);
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

  it("clicking concept chip calls tagConcept or untagConcept", () => {
    mockGetTagsForConcept.mockImplementation((conceptId: string) => {
      if (conceptId === "c1") return [mockTags[0]];
      return [];
    });

    render(<TagManager isOpen={true} onClose={() => {}} />);

    // Select a tag first
    const tagRow = screen.getByTestId("tag-row-t1");
    fireEvent.click(tagRow);

    // Click an untagged concept
    const chipC2 = screen.getByTestId("concept-chip-c2");
    fireEvent.click(chipC2);
    expect(mockTagConcept).toHaveBeenCalledWith("t1", "c2");

    // Click a tagged concept
    const chipC1 = screen.getByTestId("concept-chip-c1");
    fireEvent.click(chipC1);
    expect(mockUntagConcept).toHaveBeenCalledWith("t1", "c1");
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
