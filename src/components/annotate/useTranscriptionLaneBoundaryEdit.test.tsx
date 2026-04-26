// @vitest-environment jsdom
import { act, render } from "@testing-library/react";
import type { RefObject } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LaneKind } from "../../stores/transcriptionLanesStore";
import type { LaneStrip } from "./TranscriptionLaneRow";
import { useTranscriptionLaneBoundaryEdit } from "./useTranscriptionLaneBoundaryEdit";

afterEach(() => {
  document.body.innerHTML = "";
});

type LatestHook = ReturnType<typeof useTranscriptionLaneBoundaryEdit>;
let latestHook: LatestHook | null = null;

function makeStrip(overrides: Partial<LaneStrip> = {}): LaneStrip {
  return {
    kind: "boundaries" as LaneKind,
    label: "BND",
    tier: "ortho_words",
    intervals: [],
    boundaryOnly: true,
    ...overrides,
  };
}

function Harness({
  addInterval,
  duration = 10,
  laneEl,
  migrate,
  pxPerSec = 100,
  speaker = "Fail01",
}: {
  addInterval: ReturnType<typeof vi.fn>;
  duration?: number;
  laneEl: HTMLDivElement;
  migrate?: ReturnType<typeof vi.fn>;
  pxPerSec?: number;
  speaker?: string;
}) {
  const laneScrollRefs = {
    current: {
      ipa_phone: null,
      ipa: null,
      stt: null,
      ortho: null,
      stt_words: null,
      boundaries: laneEl,
    },
  } as RefObject<Record<LaneKind, HTMLDivElement | null>>;
  const strip = makeStrip({ needsMigration: Boolean(migrate), migrate });
  latestHook = useTranscriptionLaneBoundaryEdit({
    addInterval,
    duration,
    laneScrollRefs,
    pxPerSec,
    speaker,
    stripByKind: (kind) => (kind === strip.kind ? strip : undefined),
  });
  return null;
}

describe("useTranscriptionLaneBoundaryEdit", () => {
  it("starts a pending drag from the clicked lane position", () => {
    const addInterval = vi.fn();
    const laneEl = document.createElement("div");
    render(<Harness addInterval={addInterval} laneEl={laneEl} pxPerSec={80} />);

    act(() => {
      latestHook?.beginDrag(makeStrip(), {
        nativeEvent: { offsetX: 160 },
        preventDefault: vi.fn(),
      } as never);
    });

    expect(latestHook?.pendingDrag).toEqual({
      kind: "boundaries",
      tier: "ortho_words",
      startSec: 2,
      endSec: 2,
    });
  });

  it("commits a manually adjusted interval after a long enough drag", () => {
    const addInterval = vi.fn();
    const migrate = vi.fn();
    const laneEl = document.createElement("div");
    laneEl.scrollLeft = 0;
    laneEl.getBoundingClientRect = () => ({
      left: 10,
      top: 0,
      right: 410,
      bottom: 20,
      width: 400,
      height: 20,
      x: 10,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;

    render(<Harness addInterval={addInterval} laneEl={laneEl} migrate={migrate} pxPerSec={100} />);

    act(() => {
      latestHook?.beginDrag(makeStrip({ needsMigration: true, migrate }), {
        nativeEvent: { offsetX: 100 },
        preventDefault: vi.fn(),
      } as never);
    });

    act(() => {
      window.dispatchEvent(new MouseEvent("mousemove", { clientX: 170 }));
    });
    act(() => {
      window.dispatchEvent(new MouseEvent("mouseup"));
    });

    expect(migrate).toHaveBeenCalledTimes(1);
    expect(addInterval).toHaveBeenCalledWith("Fail01", "ortho_words", {
      start: 1,
      end: 1.6,
      text: "",
      manuallyAdjusted: true,
    });
    expect(latestHook?.pendingDrag).toBeNull();
  });

  it("drops short drags without creating an interval", () => {
    const addInterval = vi.fn();
    const laneEl = document.createElement("div");
    laneEl.scrollLeft = 0;
    laneEl.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      right: 200,
      bottom: 20,
      width: 200,
      height: 20,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;

    render(<Harness addInterval={addInterval} laneEl={laneEl} pxPerSec={100} />);

    act(() => {
      latestHook?.beginDrag(makeStrip(), {
        nativeEvent: { offsetX: 50 },
        preventDefault: vi.fn(),
      } as never);
    });

    act(() => {
      window.dispatchEvent(new MouseEvent("mousemove", { clientX: 54 }));
    });
    act(() => {
      window.dispatchEvent(new MouseEvent("mouseup"));
    });

    expect(addInterval).not.toHaveBeenCalled();
    expect(latestHook?.pendingDrag).toBeNull();
  });
});
