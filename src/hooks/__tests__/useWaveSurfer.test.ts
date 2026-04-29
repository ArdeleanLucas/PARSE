// @vitest-environment jsdom
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.hoisted ensures these are available inside vi.mock factories (which are hoisted)
const { mockWsInstance, mockRegionInstance, mockRegionsPlugin, mockSetState, mockDisableQuickRetimeSelection } =
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
      setVolume: vi.fn(),
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

    const mockDisableQuickRetimeSelection = vi.fn();
    const mockRegionsPlugin = {
      on: vi.fn(),
      addRegion: vi.fn(() => mockRegionInstance),
      enableDragSelection: vi.fn(() => mockDisableQuickRetimeSelection),
    };

    const mockSetState = vi.fn();

    return { mockWsInstance, mockRegionInstance, mockRegionsPlugin, mockSetState, mockDisableQuickRetimeSelection };
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

  it("setVolume forwards to ws.setVolume", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => {
      result.current.setVolume(0.5);
    });

    expect(mockWsInstance.setVolume).toHaveBeenCalledWith(0.5);
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
  // The Annotate Play button passes (start, end) of the active lexeme
  // region into playClip(). The first press after addRegion seeks to
  // start and stops at end. Subsequent presses (after auto-stop or any
  // waveform interaction) fall through to normal continuous playback.

  function findHandler(eventName: string): ((arg: unknown) => void) | undefined {
    const call = mockWsInstance.on.mock.calls.find(([name]) => name === eventName);
    return call?.[1] as ((arg: unknown) => void) | undefined;
  }

  it("addRegion + playClip seeks to lexeme start and pauses at end", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    // Selecting a lexeme primes the next Play press.
    act(() => {
      result.current.addRegion(2, 4, "lex-1");
    });

    let started = false;
    act(() => {
      started = result.current.playClip(2, 4) as boolean;
    });
    expect(started).toBe(true);
    // duration mock = 10, start = 2, so seekTo(0.2)
    expect(mockWsInstance.seekTo).toHaveBeenCalledWith(0.2);
    expect(mockWsInstance.play).toHaveBeenCalledTimes(1);

    const onTime = findHandler("timeupdate");
    expect(onTime).toBeDefined();

    act(() => onTime!(3.5));
    expect(mockWsInstance.pause).not.toHaveBeenCalled();

    act(() => onTime!(4.0));
    expect(mockWsInstance.pause).toHaveBeenCalledTimes(1);

    // Subsequent ticks must not double-pause.
    act(() => onTime!(4.2));
    expect(mockWsInstance.pause).toHaveBeenCalledTimes(1);
  });

  it("second playClip after clip auto-stop continues without seeking back", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => result.current.addRegion(2, 4, "lex-2"));
    act(() => {
      result.current.playClip(2, 4);
    });
    // Clip auto-stop fires the wavesurfer 'pause' handler, which clears
    // the primed flag so the next press is unbounded.
    const onPause = findHandler("pause");
    act(() => onPause!(null));

    mockWsInstance.seekTo.mockClear();
    mockWsInstance.play.mockClear();

    let started = false;
    act(() => {
      started = result.current.playClip(2, 4) as boolean;
    });

    expect(started).toBe(false);
    expect(mockWsInstance.seekTo).not.toHaveBeenCalled();
    expect(mockWsInstance.play).toHaveBeenCalledTimes(1);
  });

  it("waveform 'interaction' clears the primed state so next play stays put", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    act(() => result.current.addRegion(2, 4, "lex-3"));
    const onInteraction = findHandler("interaction");
    act(() => onInteraction!(null));

    let started = false;
    act(() => {
      started = result.current.playClip(2, 4) as boolean;
    });

    expect(started).toBe(false);
    expect(mockWsInstance.seekTo).not.toHaveBeenCalled();
    expect(mockWsInstance.play).toHaveBeenCalledTimes(1);
  });

  it("programmatic seek (e.g. ParseUI auto-positions to start) does NOT consume priming", () => {
    const { result } = renderHook(() =>
      useWaveSurfer({
        containerRef: makeContainerRef(),
        audioUrl: "/audio/test.wav",
      }),
    );

    // Simulate ParseUI's onLexemeSelected flow: addRegion → seek to start.
    act(() => result.current.addRegion(2, 4, "lex-4"));
    act(() => result.current.seek(2));

    mockWsInstance.seekTo.mockClear();

    let started = false;
    act(() => {
      started = result.current.playClip(2, 4) as boolean;
    });

    expect(started).toBe(true);
    // playClip re-seeks to start defensively — fine, cursor's already there.
    expect(mockWsInstance.seekTo).toHaveBeenCalledWith(0.2);
  });


  it("Escape clears the transient quick-retime region without removing the active lexeme region", () => {
    const { result, rerender } = renderHook(
      (props: { enabled: boolean }) =>
        useWaveSurfer({
          containerRef: makeContainerRef(),
          audioUrl: "/audio/test.wav",
          quickRetimeSelection: props.enabled
            ? {
                enabled: true,
                label: "Update water timestamp",
                onContextMenu: vi.fn(),
              }
            : null,
        }),
      { initialProps: { enabled: false } },
    );

    act(() => result.current.addRegion(2, 4, "lexeme-active"));
    mockRegionInstance.remove.mockClear();
    rerender({ enabled: true });

    const transientRegion = {
      id: "quick-retime-selection-test",
      start: 1.75,
      end: 2.75,
      element: document.createElement("div"),
      play: vi.fn(),
      remove: vi.fn(),
    };
    for (const [, handler] of mockRegionsPlugin.on.mock.calls.filter(([name]) => name === "region-created")) {
      act(() => handler(transientRegion));
    }

    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(transientRegion.remove).toHaveBeenCalledTimes(1);
    expect(mockRegionInstance.remove).not.toHaveBeenCalled();
  });

  it("enables drag selection with a transient region that does not replace the active lexeme region", () => {
    const onContextMenu = vi.fn();
    const { result, rerender, unmount } = renderHook(
      (props: { enabled: boolean }) =>
        useWaveSurfer({
          containerRef: makeContainerRef(),
          audioUrl: "/audio/test.wav",
          quickRetimeSelection: props.enabled
            ? {
                enabled: true,
                label: "Update water timestamp",
                onContextMenu,
              }
            : null,
        }),
      { initialProps: { enabled: false } },
    );

    act(() => result.current.addRegion(2, 4, "lexeme-active"));
    mockRegionInstance.remove.mockClear();

    rerender({ enabled: true });

    expect(mockRegionsPlugin.enableDragSelection).toHaveBeenCalledWith(
      expect.objectContaining({ id: expect.stringContaining("quick-retime-selection"), drag: false, resize: true }),
      1,
    );

    const transientElement = document.createElement("div");
    const transientRegion = {
      id: "quick-retime-selection-test",
      start: 1.75,
      end: 2.75,
      element: transientElement,
      play: vi.fn(),
      remove: vi.fn(),
    };

    for (const [, handler] of mockRegionsPlugin.on.mock.calls.filter(([name]) => name === "region-created")) {
      act(() => handler(transientRegion));
    }

    expect(mockRegionInstance.remove).not.toHaveBeenCalled();
    expect(transientElement.getAttribute("aria-label")).toBe("Update water timestamp");

    const contextEvent = new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 10, clientY: 20 });
    transientElement.dispatchEvent(contextEvent);
    expect(contextEvent.defaultPrevented).toBe(true);
    expect(onContextMenu).toHaveBeenCalledWith({ start: 1.75, end: 2.75 }, contextEvent);

    unmount();
    expect(mockDisableQuickRetimeSelection).toHaveBeenCalled();
    expect(transientRegion.remove).toHaveBeenCalled();
  });
});
