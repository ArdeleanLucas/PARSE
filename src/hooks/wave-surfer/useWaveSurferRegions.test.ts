// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWaveSurferRegions } from "./useWaveSurferRegions";
import type { WaveSurferRefs, WsRegion } from "./types";
import { WAVE_SURFER_DRAFT_REGION_COLOR } from "./types";

type RegionEvent = "region-created" | "region-updated";
type RegionHandler = (region: WsRegion) => void;

function makeRegion(overrides: Partial<WsRegion> & { id: string }): WsRegion {
  return {
    id: overrides.id,
    start: overrides.start ?? 1,
    end: overrides.end ?? 2,
    element: overrides.element ?? document.createElement("div"),
    play: overrides.play ?? vi.fn(),
    remove: overrides.remove ?? vi.fn(),
  };
}

function makeHarness() {
  const handlers: Array<{ event: RegionEvent; handler: RegionHandler; unsubscribe: ReturnType<typeof vi.fn> }> = [];
  const disableSelection = vi.fn();
  const regions = {
    enableDragSelection: vi.fn(() => disableSelection),
    on: vi.fn((event: RegionEvent, handler: RegionHandler) => {
      const unsubscribe = vi.fn();
      handlers.push({ event, handler, unsubscribe });
      return unsubscribe;
    }),
    addRegion: vi.fn(),
  };
  const refs: WaveSurferRefs = {
    wsRef: { current: null },
    regionsRef: { current: regions as never },
    activeRegionRef: { current: null },
    abortControllerRef: { current: null },
    clipEndRef: { current: null },
    regionPrimedRef: { current: false },
  };
  const fire = (event: RegionEvent, region: WsRegion) => {
    for (const entry of handlers.filter((candidate) => candidate.event === event)) {
      entry.handler(region);
    }
  };
  return { refs, regions, handlers, disableSelection, fire };
}

describe("useWaveSurferRegions region paths", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("wires drag-to-create contextmenu through the draft region path", () => {
    const harness = makeHarness();
    const onRegionCreated = vi.fn();
    const onRegionUpdated = vi.fn();
    const onContextMenu = vi.fn();
    const { result } = renderHook(() => useWaveSurferRegions(harness.refs));

    act(() => {
      result.current.enableDragToCreate({ onRegionCreated, onRegionUpdated, onContextMenu });
    });

    expect(harness.regions.enableDragSelection).toHaveBeenCalledWith(
      expect.objectContaining({
        id: expect.stringContaining("create-lexeme-selection"),
        color: WAVE_SURFER_DRAFT_REGION_COLOR,
        drag: true,
        resize: true,
      }),
      1,
    );

    const region = makeRegion({ id: "create-lexeme-selection-test", start: 1.25, end: 2.5 });
    act(() => harness.fire("region-created", region));

    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    region.element!.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(onRegionCreated).toHaveBeenCalledWith({ start: 1.25, end: 2.5 });
    expect(onContextMenu).toHaveBeenCalledWith({ start: 1.25, end: 2.5 }, event);
  });

  it("wires quick-retime contextmenu through the retime region path", () => {
    const harness = makeHarness();
    const onContextMenu = vi.fn();
    renderHook(() =>
      useWaveSurferRegions(harness.refs, {
        enabled: true,
        label: "Update water timestamp",
        onContextMenu,
      }),
    );

    expect(harness.regions.enableDragSelection).toHaveBeenCalledWith(
      expect.objectContaining({ id: expect.stringContaining("quick-retime-selection"), drag: false, resize: true }),
      1,
    );

    const region = makeRegion({ id: "quick-retime-selection-test", start: 3.25, end: 4.5 });
    act(() => harness.fire("region-created", region));

    expect(region.element!.getAttribute("aria-label")).toBe("Update water timestamp");
    expect(region.element!.getAttribute("title")).toBe("Update water timestamp");

    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    region.element!.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(onContextMenu).toHaveBeenCalledWith({ start: 3.25, end: 4.5 }, event);
  });

  it("cleans up quick-retime listeners and removes the transient region", () => {
    const harness = makeHarness();
    const onContextMenu = vi.fn();
    const region = makeRegion({ id: "quick-retime-selection-test", start: 5, end: 6 });
    const { unmount } = renderHook(() =>
      useWaveSurferRegions(harness.refs, {
        enabled: true,
        label: "Update water timestamp",
        onContextMenu,
      }),
    );

    act(() => harness.fire("region-created", region));
    unmount();

    expect(region.remove).toHaveBeenCalledTimes(1);
    expect(harness.disableSelection).toHaveBeenCalledTimes(1);
    expect(harness.handlers.find((entry) => entry.event === "region-created")?.unsubscribe).toHaveBeenCalledTimes(1);

    const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    region.element!.dispatchEvent(event);
    expect(onContextMenu).not.toHaveBeenCalled();
  });

  it("lets create and retime region paths coexist without routing events to the wrong callback", () => {
    const harness = makeHarness();
    const onCreateContextMenu = vi.fn();
    const onRetimeContextMenu = vi.fn();
    const onRegionCreated = vi.fn();
    const { result } = renderHook(() =>
      useWaveSurferRegions(harness.refs, {
        enabled: true,
        label: "Update water timestamp",
        onContextMenu: onRetimeContextMenu,
      }),
    );

    act(() => {
      result.current.enableDragToCreate({
        onRegionCreated,
        onRegionUpdated: vi.fn(),
        onContextMenu: onCreateContextMenu,
      });
    });

    const retimeRegion = makeRegion({ id: "quick-retime-selection-test", start: 1, end: 2 });
    const createRegion = makeRegion({ id: "create-lexeme-selection-test", start: 3, end: 4 });
    act(() => {
      harness.fire("region-created", retimeRegion);
      harness.fire("region-created", createRegion);
    });

    const retimeEvent = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    const createEvent = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    retimeRegion.element!.dispatchEvent(retimeEvent);
    createRegion.element!.dispatchEvent(createEvent);

    expect(onRegionCreated).toHaveBeenCalledTimes(1);
    expect(onRegionCreated).toHaveBeenCalledWith({ start: 3, end: 4 });
    expect(onRetimeContextMenu).toHaveBeenCalledTimes(1);
    expect(onRetimeContextMenu).toHaveBeenCalledWith({ start: 1, end: 2 }, retimeEvent);
    expect(onCreateContextMenu).toHaveBeenCalledTimes(1);
    expect(onCreateContextMenu).toHaveBeenCalledWith({ start: 3, end: 4 }, createEvent);
  });
});
