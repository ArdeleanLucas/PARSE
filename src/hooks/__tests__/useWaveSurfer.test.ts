// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.hoisted ensures these are available inside vi.mock factories (which are hoisted)
const { mockWsInstance, mockRegionInstance, mockRegionsPlugin, mockSetState } =
  vi.hoisted(() => {
    const mockViewport = document.createElement("div");
    Object.defineProperty(mockViewport, "clientWidth", { value: 200, configurable: true });
    mockViewport.scrollLeft = 0;
    const mockWrapper = document.createElement("div");
    mockViewport.appendChild(mockWrapper);

    const mockWsInstance = {
      play: vi.fn(),
      pause: vi.fn(),
      playPause: vi.fn(),
      destroy: vi.fn(),
      load: vi.fn(),
      seekTo: vi.fn(),
      zoom: vi.fn(),
      setPlaybackRate: vi.fn(),
      setScroll: vi.fn(),
      getDuration: vi.fn(() => 10),
      getCurrentTime: vi.fn(() => 0),
      getWrapper: vi.fn(() => mockWrapper),
      on: vi.fn(),
      options: { minPxPerSec: 100 },
    };

    const mockRegionInstance = {
      remove: vi.fn(),
      play: vi.fn(),
      id: "test-region",
      start: 1,
      end: 3,
    };

    const mockRegionsPlugin = {
      on: vi.fn(),
      addRegion: vi.fn(() => mockRegionInstance),
    };

    const mockSetState = vi.fn();

    return { mockWsInstance, mockRegionInstance, mockRegionsPlugin, mockSetState };
  });

vi.mock("wavesurfer.js", () => ({
  default: {
    create: vi.fn(() => mockWsInstance),
  },
}));

vi.mock("wavesurfer.js/dist/plugins/regions.js", () => ({
  default: {
    create: vi.fn(() => mockRegionsPlugin),
  },
}));

vi.mock("wavesurfer.js/dist/plugins/timeline.js", () => ({
  default: {
    create: vi.fn(() => ({})),
  },
}));

vi.mock("../../stores/playbackStore", () => ({
  usePlaybackStore: { setState: mockSetState },
}));

// Import after mocks
import { useWaveSurfer } from "../useWaveSurfer";
import WaveSurfer from "wavesurfer.js";

function makeContainerRef() {
  return { current: document.createElement("div") };
}

describe("useWaveSurfer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockWsInstance.getDuration.mockReturnValue(10);
  });

  it("destroys on unmount", () => {
    const { unmount } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    unmount();
    expect(mockWsInstance.destroy).toHaveBeenCalledTimes(1);
  });

  it("reinitializes on audioUrl change", () => {
    const containerRef = makeContainerRef();
    const { rerender } = renderHook(
      (props: { audioUrl: string }) =>
        useWaveSurfer({ containerRef, audioUrl: props.audioUrl }),
      { initialProps: { audioUrl: "/audio/a.wav" } },
    );

    rerender({ audioUrl: "/audio/b.wav" });

    // First instance created, then destroyed on re-init, then second created
    expect(WaveSurfer.create).toHaveBeenCalledTimes(2);
    expect(mockWsInstance.destroy).toHaveBeenCalledTimes(1);
  });

  it("play() calls ws.play", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => {
      result.current.play();
    });

    expect(mockWsInstance.play).toHaveBeenCalledTimes(1);
  });

  it("seek(5) calls ws.seekTo(0.5) when duration=10", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => {
      result.current.seek(5);
    });

    expect(mockWsInstance.seekTo).toHaveBeenCalledWith(0.5);
  });

  it("clearRegions() removes active region", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    // Add a region first so activeRegionRef is populated
    act(() => {
      result.current.addRegion(1, 3, "r-test");
    });

    act(() => {
      result.current.clearRegions();
    });

    expect(mockRegionInstance.remove).toHaveBeenCalled();
  });

  it("mouse wheel scrolls the waveform horizontally", () => {
    const containerRef = makeContainerRef();

    renderHook(() =>
      useWaveSurfer({
        containerRef,
        audioUrl: "/audio/test.wav",
      }),
    );

    const event = new WheelEvent("wheel", { deltaY: 120, cancelable: true });
    act(() => {
      containerRef.current!.dispatchEvent(event);
    });

    expect(event.defaultPrevented).toBe(true);
    expect(mockWsInstance.setScroll).toHaveBeenCalledWith(120);
  });
});
