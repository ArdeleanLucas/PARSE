// @vitest-environment jsdom
import { act, render } from "@testing-library/react";
import { createRef } from "react";
import type { RefObject } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LaneKind } from "../../stores/transcriptionLanesStore";
import type { LaneStrip } from "./TranscriptionLaneRow";
import { useTranscriptionLaneInlineEdit } from "./useTranscriptionLaneInlineEdit";

afterEach(() => {
  document.body.innerHTML = "";
});

type LatestHook = ReturnType<typeof useTranscriptionLaneInlineEdit>;
let latestHook: LatestHook | null = null;

function makeStrip(overrides: Partial<LaneStrip> = {}): LaneStrip {
  return {
    kind: "stt" as LaneKind,
    label: "STT",
    tier: "stt",
    intervals: [{ start: 1, end: 2, text: "segment text" }],
    sourceIndices: [4],
    ...overrides,
  };
}

function Harness({
  editRef,
  speaker = "Fail01",
  strip = makeStrip(),
  updateInterval,
}: {
  editRef: RefObject<HTMLSpanElement | null>;
  speaker?: string;
  strip?: LaneStrip;
  updateInterval: ReturnType<typeof vi.fn>;
}) {
  latestHook = useTranscriptionLaneInlineEdit({ editRef, speaker, updateInterval });
  return (
    <button
      type="button"
      onClick={() => latestHook?.beginIntervalEdit(strip, 4)}
    >
      start
    </button>
  );
}

describe("useTranscriptionLaneInlineEdit", () => {
  it("enters editing mode only for non-boundary lanes and migrates first when needed", () => {
    const updateInterval = vi.fn();
    const editRef = createRef<HTMLSpanElement>();
    const migrate = vi.fn();
    const { getByRole, rerender } = render(
      <Harness editRef={editRef} updateInterval={updateInterval} strip={makeStrip({ needsMigration: true, migrate })} />,
    );

    act(() => {
      getByRole("button", { name: "start" }).click();
    });

    expect(migrate).toHaveBeenCalledTimes(1);
    expect(latestHook?.editing).toEqual({ kind: "stt", index: 4 });

    rerender(
      <Harness
        editRef={editRef}
        updateInterval={updateInterval}
        strip={makeStrip({ kind: "boundaries", label: "BND", boundaryOnly: true, tier: "ortho_words" })}
      />,
    );
    act(() => {
      getByRole("button", { name: "start" }).click();
    });
    expect(latestHook?.editing).toEqual({ kind: "stt", index: 4 });
  });

  it("commits trimmed text and clears editing state", () => {
    const updateInterval = vi.fn();
    const editRef = createRef<HTMLSpanElement>();
    render(<Harness editRef={editRef} updateInterval={updateInterval} />);

    act(() => {
      latestHook?.beginIntervalEdit(makeStrip(), 4);
    });
    act(() => {
      latestHook?.commitEdit("stt", 4, "  edited text  ");
    });

    expect(updateInterval).toHaveBeenCalledWith("Fail01", "stt", 4, "edited text");
    expect(latestHook?.editing).toBeNull();
  });

  it("focuses and select-all highlights the inline editor when editing starts", () => {
    const updateInterval = vi.fn();
    const editRef = createRef<HTMLSpanElement>();
    const span = document.createElement("span");
    span.textContent = "segment text";
    document.body.appendChild(span);
    (editRef as { current: HTMLSpanElement | null }).current = span;
    const focusSpy = vi.spyOn(span, "focus");

    render(<Harness editRef={editRef} updateInterval={updateInterval} />);

    act(() => {
      latestHook?.beginIntervalEdit(makeStrip(), 4);
    });

    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(window.getSelection()?.toString()).toBe("segment text");
  });
});
