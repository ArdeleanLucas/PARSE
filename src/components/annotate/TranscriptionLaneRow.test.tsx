// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LaneKind } from "../../stores/transcriptionLanesStore";
import { TranscriptionLaneRow, type LaneStrip } from "./TranscriptionLaneRow";

function makeStrip(overrides: Partial<LaneStrip> = {}): LaneStrip {
  return {
    kind: "stt" as LaneKind,
    label: "STT",
    intervals: [{ start: 1, end: 2, text: "segment text" }],
    sourceIndices: [4],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  document.documentElement.classList.remove('theme-amber', 'theme-violet', 'theme-blue', 'dark');
});

function renderLaneRow(overrides: Partial<Parameters<typeof TranscriptionLaneRow>[0]> = {}) {
  const strip = makeStrip(overrides.strip as Partial<LaneStrip> | undefined);
  return render(
    <TranscriptionLaneRow
      color="#059669"
      editing={null}
      firstIdx={0}
      innerWidth={1200}
      isEmpty={false}
      pendingDrag={null}
      pxPerSec={120}
      selectedInterval={null}
      showEmptyHint={false}
      speaker="Fail01"
      strip={strip}
      visible={strip.intervals}
      visibleSourceIndices={strip.sourceIndices}
      onBeginDrag={vi.fn()}
      onCommitEdit={vi.fn()}
      onContextMenu={vi.fn()}
      onDoubleClickInterval={vi.fn()}
      onSeekInterval={vi.fn()}
      setEditRef={vi.fn()}
      setEditing={vi.fn()}
      setLaneScrollRef={vi.fn()}
      {...overrides}
    />,
  );
}

describe("TranscriptionLaneRow", () => {
  it("renders the lane label and visible interval text", () => {
    render(
      <TranscriptionLaneRow
        color="#1d4ed8"
        editing={null}
        firstIdx={0}
        innerWidth={1200}
        isEmpty={false}
        pendingDrag={null}
        pxPerSec={120}
        selectedInterval={null}
        showEmptyHint={false}
        speaker="Fail01"
        strip={makeStrip()}
        visible={makeStrip().intervals}
        visibleSourceIndices={[4]}
        onBeginDrag={vi.fn()}
        onCommitEdit={vi.fn()}
        onContextMenu={vi.fn()}
        onDoubleClickInterval={vi.fn()}
        onSeekInterval={vi.fn()}
        setEditRef={vi.fn()}
        setEditing={vi.fn()}
        setLaneScrollRef={vi.fn()}
      />,
    );

    expect(screen.getByTitle("STT lane")).toBeTruthy();
    expect(screen.getByRole("button", { name: "STT 1.00s: segment text" })).toBeTruthy();
    expect(screen.getByText("segment text")).toBeTruthy();
  });

  it("renders the empty hint overlay when a lane has no intervals", () => {
    render(
      <TranscriptionLaneRow
        color="#059669"
        editing={null}
        firstIdx={0}
        innerWidth={1200}
        isEmpty
        pendingDrag={null}
        pxPerSec={120}
        selectedInterval={null}
        showEmptyHint
        speaker="Fail01"
        strip={makeStrip({ kind: "boundaries", label: "BND", intervals: [], boundaryOnly: true })}
        visible={[]}
        visibleSourceIndices={[]}
        emptyMsg="Run forced-align first"
        onBeginDrag={vi.fn()}
        onCommitEdit={vi.fn()}
        onContextMenu={vi.fn()}
        onDoubleClickInterval={vi.fn()}
        onSeekInterval={vi.fn()}
        setEditRef={vi.fn()}
        setEditing={vi.fn()}
        setLaneScrollRef={vi.fn()}
      />,
    );

    expect(screen.getByText("Run forced-align first")).toBeTruthy();
  });

  it("surfaces constant-fallback confidence provenance on intervals", () => {
    renderLaneRow({
      strip: makeStrip({
        intervals: [{ start: 1, end: 2, text: "fallback", confidenceSource: "constant_fallback", confidenceNTokens: 0 }],
      }),
    });

    const marker = screen.getByTestId("confidence-fallback-marker");
    expect(marker.textContent).toBe("fallback confidence");
    expect(screen.getByRole("button", { name: /fallback confidence/i })).toBeTruthy();
  });

  it("delegates interval clicks and drag starts through its callbacks", () => {
    const onSeekInterval = vi.fn();
    const onBeginDrag = vi.fn();

    const { container } = render(
      <TranscriptionLaneRow
        color="#7c3aed"
        editing={null}
        firstIdx={0}
        innerWidth={1200}
        isEmpty={false}
        pendingDrag={null}
        pxPerSec={120}
        selectedInterval={null}
        showEmptyHint={false}
        speaker="Fail01"
        strip={makeStrip({ kind: "stt_words", label: "Words", boundaryOnly: true, intervals: [{ start: 2, end: 2.5, text: "" }] })}
        visible={[{ start: 2, end: 2.5, text: "" }]}
        visibleSourceIndices={[0]}
        onBeginDrag={onBeginDrag}
        onCommitEdit={vi.fn()}
        onContextMenu={vi.fn()}
        onDoubleClickInterval={vi.fn()}
        onSeekInterval={onSeekInterval}
        setEditRef={vi.fn()}
        setEditing={vi.fn()}
        setLaneScrollRef={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Words 2.00s" }));
    expect(onSeekInterval).toHaveBeenCalledWith({ start: 2, end: 2.5, text: "" }, 0, "stt_words");

    const timeline = container.querySelector(".relative.h-full") as HTMLElement;
    fireEvent.mouseDown(timeline, {
      button: 0,
      nativeEvent: { offsetX: 240 },
    });
    expect(onBeginDrag).toHaveBeenCalled();
  });

  it("updates lane segment styling when the dark theme class changes after mount", async () => {
    renderLaneRow();

    const segment = screen.getByRole("button", { name: "STT 1.00s: segment text" });
    expect(segment.getAttribute("style") ?? "").toContain("background-color: rgb(");
    expect(segment.getAttribute("style") ?? "").toContain("color: rgb(51, 65, 85)");

    await act(async () => {
      document.documentElement.classList.add("theme-amber");
      await Promise.resolve();
    });

    const updatedStyle = segment.getAttribute("style") ?? "";
    expect(updatedStyle).toContain("background-color: var(--bg-surface)");
    expect(updatedStyle).toContain("border-left: 3px solid rgb(5, 150, 105)");
    expect(updatedStyle).toContain("color: rgb(5, 150, 105)");
    expect(updatedStyle).toContain("font-weight: 500");
  });

  it("renders pending drag regions with a neutral dark background in dark themes", () => {
    document.documentElement.classList.add("theme-amber");
    const { container } = renderLaneRow({
      pendingDrag: { kind: "stt", tier: "stt", startSec: 1, endSec: 1.5 },
    });

    const pending = container.querySelector(".border-dashed") as HTMLElement;
    expect(pending.getAttribute("style") ?? "").toContain("background-color: rgba(0, 0, 0, 0.25)");
  });

});
