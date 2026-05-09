// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  TranscriptionRunModal,
  type TranscriptionRunConfirm,
} from "../TranscriptionRunModal";

vi.mock("../../../api/client", () => ({
  getAnnotation: vi.fn(),
  getPipelineState: vi.fn(),
  getConceptsByTag: vi.fn(),
}));

vi.mock("../../../stores/tagStore", () => ({
  useTagStore: vi.fn(),
}));

import { getAnnotation, getConceptsByTag, getPipelineState } from "../../../api/client";
import { useTagStore } from "../../../stores/tagStore";

const TAG_VOCABULARY = [
  { id: "t-thesis", label: "Thesis", color: "#10b981" },
  { id: "t-wordlist", label: "WordList", color: "#3b82f6" },
  { id: "t-mystery", label: "Mystery", color: "#f59e0b" },
];

function makeReadyState(speaker: string) {
  return {
    speaker,
    normalize: { done: true, can_run: true, reason: null, path: `audio/working/${speaker}/${speaker}.wav` },
    stt: { done: true, can_run: true, reason: null, segments: 4 },
    ortho: { done: true, can_run: true, reason: null, intervals: 4 },
    ipa: { done: true, can_run: true, reason: null, intervals: 4 },
  };
}

function buildPreviewResponse() {
  return {
    totalConcepts: 2,
    perSpeaker: {
      Alpha: {
        conceptCount: 2,
        concepts: [
          { conceptId: "c1", name: "root", start: 1.0, end: 2.0, tags: ["Thesis"] },
          { conceptId: "c2", name: "leaf", start: 3.0, end: 4.0, tags: ["Thesis", "WordList"] },
        ],
      },
      Beta: { conceptCount: 0, concepts: [] },
    },
    unknownTags: [],
    ambiguousTags: {},
  };
}

async function renderTaggedOnlyOpen(onConfirm = vi.fn<[TranscriptionRunConfirm], void>()) {
  render(
    <TranscriptionRunModal
      open={true}
      onClose={() => {}}
      onConfirm={onConfirm}
      speakers={["Alpha", "Beta"]}
      defaultSelectedSpeaker="Alpha"
      title="Run Full Pipeline"
    />,
  );

  // Wait for pipeline state to settle so the speaker checkbox row is rendered.
  await waitFor(() => expect(getPipelineState).toHaveBeenCalled());

  // Switch run mode to tagged-only.
  fireEvent.click(screen.getByTestId("transcription-run-mode-tagged-only"));
  return { onConfirm };
}

describe("TranscriptionRunModal — tagged-only mode", () => {
  beforeEach(() => {
    vi.mocked(getPipelineState).mockReset();
    vi.mocked(getAnnotation).mockReset();
    vi.mocked(getConceptsByTag).mockReset();
    (useTagStore as unknown as { mockImplementation: (fn: unknown) => void })
      .mockImplementation((selector?: (state: { tags: typeof TAG_VOCABULARY }) => unknown) => {
        const state = { tags: TAG_VOCABULARY };
        return typeof selector === "function" ? selector(state) : state;
      });
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) => makeReadyState(speaker));
    vi.mocked(getAnnotation).mockResolvedValue({
      speaker: "Alpha",
      tiers: { concept: { name: "concept", display_order: 0, intervals: [] } },
    });
    vi.mocked(getConceptsByTag).mockResolvedValue(buildPreviewResponse());
  });

  afterEach(() => {
    cleanup();
  });

  it("(a) switching runMode reveals tag picker, match selector, and preview section", async () => {
    await renderTaggedOnlyOpen();
    expect(screen.getByTestId("transcription-run-tagged-controls")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-tagged-picker-trigger")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-tagged-match")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-tagged-match-any")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-tagged-match-all")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-tagged-preview")).toBeTruthy();
  });

  it("(b) selecting two tags fires getConceptsByTag with chosen labels and default match=any", async () => {
    await renderTaggedOnlyOpen();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-Thesis").querySelector("input")!);
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-WordList").querySelector("input")!);

    await waitFor(() => expect(getConceptsByTag).toHaveBeenCalled());
    const calls1 = vi.mocked(getConceptsByTag).mock.calls;
    const lastCall = calls1[calls1.length - 1][0];
    expect(lastCall).toEqual({
      speakers: ["Alpha"],
      tagLabels: ["Thesis", "WordList"],
      match: "any",
    });
  });

  it("(c) toggling match selector to ALL re-fires getConceptsByTag with match=all", async () => {
    await renderTaggedOnlyOpen();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-Thesis").querySelector("input")!);

    await waitFor(() => expect(getConceptsByTag).toHaveBeenCalled());
    vi.mocked(getConceptsByTag).mockClear();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-match-all"));

    await waitFor(() => expect(getConceptsByTag).toHaveBeenCalled());
    const calls2 = vi.mocked(getConceptsByTag).mock.calls;
    const lastCall2 = calls2[calls2.length - 1][0];
    expect(lastCall2.match).toBe("all");
    expect(lastCall2.tagLabels).toEqual(["Thesis"]);
  });

  it("(d) preview renders per-speaker count and a row per concept with tag chips", async () => {
    await renderTaggedOnlyOpen();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-Thesis").querySelector("input")!);

    const previewList = await screen.findByTestId("transcription-run-tagged-preview-list");
    const alphaSection = within(previewList).getByTestId(
      "transcription-run-tagged-preview-speaker-Alpha",
    );
    expect(alphaSection.textContent).toContain("Alpha · 2 concepts");
    expect(within(alphaSection).getByTestId("transcription-run-tagged-preview-row-Alpha-c1").textContent)
      .toContain("#c1");
    expect(within(alphaSection).getByTestId("transcription-run-tagged-preview-row-Alpha-c1").textContent)
      .toContain("Thesis");
    expect(within(alphaSection).getByTestId("transcription-run-tagged-preview-row-Alpha-c2").textContent)
      .toContain("WordList");

    const betaSection = within(previewList).getByTestId(
      "transcription-run-tagged-preview-speaker-Beta",
    );
    expect(betaSection.textContent).toContain("Beta · 0 concepts");
  });

  it("(e) with zero resolved concepts the confirm button is disabled (and the unknown-tag warning is gated by tagMatch)", async () => {
    vi.mocked(getConceptsByTag).mockResolvedValue({
      totalConcepts: 0,
      perSpeaker: { Alpha: { conceptCount: 0, concepts: [] }, Beta: { conceptCount: 0, concepts: [] } },
      unknownTags: ["Mystery"],
      ambiguousTags: {},
    });
    await renderTaggedOnlyOpen();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-Mystery").querySelector("input")!);

    await waitFor(() => expect(getConceptsByTag).toHaveBeenCalled());
    await waitFor(() => {
      const confirm = screen.getByTestId("transcription-run-confirm") as HTMLButtonElement;
      expect(confirm.disabled).toBe(true);
    });
    // Issue #8 — unknown-tag warning is rendered for non-empty unknownTags.
    const warning = await screen.findByTestId("transcription-run-tagged-preview-unknown");
    // Default match=any → benign copy.
    expect(warning.textContent).toContain("Unknown tags ignored");
    expect(warning.textContent).not.toContain("ALL match expected");
    // Issue #5 — toggling to ALL switches the copy to the stricter variant.
    fireEvent.click(screen.getByTestId("transcription-run-tagged-match-all"));
    await waitFor(() => {
      const w2 = screen.getByTestId("transcription-run-tagged-preview-unknown");
      expect(w2.textContent).toContain("ALL match expected");
    });
  });

  it("(f) confirming with non-empty preview calls onConfirm with tagged-only payload", async () => {
    const { onConfirm } = await renderTaggedOnlyOpen();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-Thesis").querySelector("input")!);
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-WordList").querySelector("input")!);

    await screen.findByTestId("transcription-run-tagged-preview-list");

    fireEvent.click(screen.getByTestId("transcription-run-tagged-match-all"));
    await waitFor(() => expect(getConceptsByTag).toHaveBeenLastCalledWith(
      expect.objectContaining({ match: "all" }),
    ));
    await screen.findByTestId("transcription-run-tagged-preview-list");

    const confirm = screen.getByTestId("transcription-run-confirm") as HTMLButtonElement;
    await waitFor(() => expect(confirm.disabled).toBe(false));
    fireEvent.click(confirm);

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const payload = onConfirm.mock.calls[0][0];
    expect(payload.runMode).toBe("tagged-only");
    expect(payload.tagLabels).toEqual(["Thesis", "WordList"]);
    expect(payload.tagMatch).toBe("all");
    expect(payload.speakers).toEqual(["Alpha"]);
    // Issue #7 — payload also pins pad (default 0.2) and the steps array.
    expect(payload.pad).toBe(0.2);
    // The default tagged-only mode runs ortho + ipa (no normalize, no stt
    // when none chosen by default).
    expect(payload.steps).toEqual(expect.arrayContaining(["ortho", "ipa"]));
    expect(payload.steps).not.toContain("normalize");
  });

  it("popover empty state when vocabulary is empty", async () => {
    (useTagStore as unknown as { mockImplementation: (fn: unknown) => void })
      .mockImplementation((selector?: (state: { tags: typeof TAG_VOCABULARY }) => unknown) => {
        const state = { tags: [] as typeof TAG_VOCABULARY };
        return typeof selector === "function" ? selector(state) : state;
      });

    await renderTaggedOnlyOpen();
    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    expect(screen.getByTestId("transcription-run-tagged-picker-empty").textContent).toContain(
      "No tags defined. Add tags from the right panel.",
    );
  });

  it("(g) ambiguousTags from preview render in a rose-700 block; confirm is disabled when match=all+ambiguous", async () => {
    vi.mocked(getConceptsByTag).mockResolvedValue({
      totalConcepts: 1,
      perSpeaker: {
        Alpha: { conceptCount: 1, concepts: [{ conceptId: "c1", name: "x", start: 0, end: 1, tags: ["Thesis"] }] },
        Beta: { conceptCount: 0, concepts: [] },
      },
      unknownTags: [],
      ambiguousTags: { Thesis: ["t1", "t2"] },
    });
    await renderTaggedOnlyOpen();

    fireEvent.click(screen.getByTestId("transcription-run-tagged-picker-trigger"));
    fireEvent.click(within(screen.getByTestId("transcription-run-tagged-picker-popover"))
      .getByTestId("transcription-run-tagged-picker-option-Thesis").querySelector("input")!);

    const ambiguous = await screen.findByTestId("transcription-run-tagged-preview-ambiguous");
    expect(ambiguous.textContent).toContain("Ambiguous tags");
    expect(ambiguous.textContent).toContain("Thesis");
    // Pick one tag id to disambiguate copy is present.
    expect(ambiguous.textContent).toContain("Pick one tag id");
    // Per-label entry is rendered with both candidate ids.
    expect(within(ambiguous).getByTestId("transcription-run-tagged-preview-ambiguous-Thesis").textContent)
      .toContain("t1");
    expect(within(ambiguous).getByTestId("transcription-run-tagged-preview-ambiguous-Thesis").textContent)
      .toContain("t2");
    // match=any (default) → confirm is enabled (totalConcepts > 0).
    let confirm = screen.getByTestId("transcription-run-tagged-match-any") as HTMLInputElement;
    expect(confirm.checked).toBe(true);
    // Toggle to match=all → ambiguous makes confirm disabled.
    fireEvent.click(screen.getByTestId("transcription-run-tagged-match-all"));
    await waitFor(() => {
      const btn = screen.getByTestId("transcription-run-confirm") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
    });
  });
});
