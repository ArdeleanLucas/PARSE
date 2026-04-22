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
      isPlaying: vi.fn(() => false),
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

  // -- Clip-bounded play --
  //
  // The Annotate "Play" button passes the active region's end into
  // playClip() so the first press plays just that lexeme. Subsequent
  // presses (cursor at end), or seeks to a different position, must fall
  // through to normal continuous playback.

  function findHandler(eventName: string): ((arg: unknown) => void) | undefined {
    const call = mockWsInstance.on.mock.calls.find(([name]) => name === eventName);
    return call?.[1] as ((arg: unknown) => void) | undefined;
  }

  it("playClip(end) starts playback and pauses at end via timeupdate", () => {
    mockWsInstance.getCurrentTime.mockReturnValue(1);
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    let started = false;
    act(() => {
      started = result.current.playClip(3) as boolean;
    });
    expect(started).toBe(true);
    expect(mockWsInstance.play).toHaveBeenCalledTimes(1);

    const onTime = findHandler("timeupdate");
    expect(onTime).toBeDefined();

    // First tick well before end — no pause yet.
    act(() => {
      onTime!(2.5);
    });
    expect(mockWsInstance.pause).not.toHaveBeenCalled();

    // Crossing end — pause exactly once.
    act(() => {
      onTime!(3.0);
    });
    expect(mockWsInstance.pause).toHaveBeenCalledTimes(1);

    // Subsequent ticks should NOT pause again (clipEnd was cleared).
    act(() => {
      onTime!(3.2);
    });
    expect(mockWsInstance.pause).toHaveBeenCalledTimes(1);
  });

  it("playClip(end) degrades to plain play when cursor is already past end", () => {
    mockWsInstance.getCurrentTime.mockReturnValue(3.5);
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    let started = false;
    act(() => {
      started = result.current.playClip(3) as boolean;
    });

    expect(started).toBe(false);
    expect(mockWsInstance.play).toHaveBeenCalledTimes(1);

    // Even at later timeupdates, no clip-bound pause should fire.
    const onTime = findHandler("timeupdate");
    act(() => onTime!(99));
    expect(mockWsInstance.pause).not.toHaveBeenCalled();
  });

  it("seek() clears any pending clip-bound so the next play is unbounded", () => {
    mockWsInstance.getCurrentTime.mockReturnValue(1);
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => {
      result.current.playClip(3);
    });
    act(() => {
      result.current.seek(7);
    });

    const onTime = findHandler("timeupdate");
    act(() => onTime!(3));
    expect(mockWsInstance.pause).not.toHaveBeenCalled();
  });

  it("waveform 'interaction' event clears the pending clip-bound", () => {
    mockWsInstance.getCurrentTime.mockReturnValue(1);
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => {
      result.current.playClip(3);
    });
    const onInteraction = findHandler("interaction");
    expect(onInteraction).toBeDefined();
    act(() => onInteraction!(null));

    const onTime = findHandler("timeupdate");
    act(() => onTime!(3));
    expect(mockWsInstance.pause).not.toHaveBeenCalled();
  });
});
