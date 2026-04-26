// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
});
