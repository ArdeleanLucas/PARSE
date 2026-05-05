// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnnotationRecord } from "../../../api/types";
import type { LexemeSearchResponse } from "../../../api/client";

const { mockSearchLexeme } = vi.hoisted(() => ({
  mockSearchLexeme: vi.fn(),
}));

let mockRecord: AnnotationRecord | null = null;
const mockSetConfirmedAnchor = vi.fn();

vi.mock("../../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/client")>()),
  searchLexeme: (...args: unknown[]) => mockSearchLexeme(...args),
}));

vi.mock("../annotate-views/useAnnotateSelection", () => ({
  useAnnotateSelection: () => ({
    activeConceptId: "1",
    activeSpeaker: "Fail02",
    concepts: [{ id: "1", label: "water" }],
    record: mockRecord,
  }),
}));

vi.mock("../../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) =>
    selector({ setConfirmedAnchor: mockSetConfirmedAnchor }),
}));

import { LexemeSearchPanel } from "../LexemeSearchPanel";

const emptyResponse: LexemeSearchResponse = {
  speaker: "Fail02",
  concept_id: "1",
  variants: ["water"],
  language: "ku",
  candidates: [],
  signals_available: { phonemizer: false, cross_speaker_anchors: 0, contact_variants: [] },
};

function renderPanel() {
  render(<LexemeSearchPanel />);
  fireEvent.change(screen.getByLabelText("Variants"), { target: { value: "water" } });
}

describe("LexemeSearchPanel tier filter", () => {
  beforeEach(() => {
    mockRecord = null;
    mockSearchLexeme.mockReset();
    mockSearchLexeme.mockResolvedValue(emptyResponse);
    mockSetConfirmedAnchor.mockClear();
  });

  afterEach(cleanup);

  it("sends no tiers option by default so the backend searches all tiers", async () => {
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(mockSearchLexeme).toHaveBeenCalledTimes(1));
    expect(mockSearchLexeme).toHaveBeenCalledWith("Fail02", ["water"], { conceptId: "1" });
    expect(mockSearchLexeme.mock.calls[0][2]).not.toHaveProperty("tiers");
  });

  it("sends only the remaining selected tiers after chips are toggled off", async () => {
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "ortho_words" }));
    fireEvent.click(screen.getByRole("button", { name: "ortho" }));
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(mockSearchLexeme).toHaveBeenCalledTimes(1));
    expect(mockSearchLexeme).toHaveBeenCalledWith("Fail02", ["water"], {
      conceptId: "1",
      tiers: ["stt", "ipa"],
    });
  });

  it("disables Search and does not call searchLexeme when all tiers are off", () => {
    renderPanel();

    for (const tier of ["ortho_words", "ortho", "stt", "ipa"]) {
      fireEvent.click(screen.getByRole("button", { name: tier }));
    }

    const searchButton = screen.getByRole("button", { name: "Search" }) as HTMLButtonElement;
    expect(searchButton.disabled).toBe(true);
    expect(screen.getByText("Select at least one tier.")).toBeTruthy();
    fireEvent.click(searchButton);
    expect(mockSearchLexeme).not.toHaveBeenCalled();
  });
});
