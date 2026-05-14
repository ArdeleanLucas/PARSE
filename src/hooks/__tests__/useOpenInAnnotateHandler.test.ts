// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useOpenInAnnotateHandler } from "../useOpenInAnnotateHandler";
import { useCompareReturnStore } from "../../stores/compareReturnStore";
import { usePlaybackStore } from "../../stores/playbackStore";

describe("useOpenInAnnotateHandler", () => {
  beforeEach(() => {
    useCompareReturnStore.getState().clear();
    usePlaybackStore.setState({
      activeSpeaker: null,
      currentTime: 0,
      pendingSeek: null,
    });
  });

  it("saves the snapshot, seeds playback, and flips mode on click", () => {
    const setCurrentMode = vi.fn();
    const { result } = renderHook(() =>
      useOpenInAnnotateHandler({
        conceptId: 12,
        conceptKey: "concept-12-key",
        setCurrentMode,
      }),
    );

    act(() => {
      result.current("SPK_02", { start_sec: 4.25, csv_row_id: "row-99" });
    });

    expect(useCompareReturnStore.getState().snapshot).toEqual({
      conceptId: 12,
      conceptKey: "concept-12-key",
      expandedSpeaker: "SPK_02",
    });

    const playback = usePlaybackStore.getState();
    expect(playback.activeSpeaker).toBe("SPK_02");
    expect(playback.pendingSeek).not.toBeNull();
    expect(playback.pendingSeek?.targetSec).toBe(4.25);
    expect(playback.pendingSeek?.nonce).toBeGreaterThan(0);

    expect(setCurrentMode).toHaveBeenCalledTimes(1);
    expect(setCurrentMode).toHaveBeenCalledWith("annotate");
  });

  it("treats a null start_sec as seek to 0", () => {
    const setCurrentMode = vi.fn();
    const { result } = renderHook(() =>
      useOpenInAnnotateHandler({
        conceptId: 1,
        conceptKey: "k1",
        setCurrentMode,
      }),
    );

    act(() => {
      result.current("SPK_01", { start_sec: null, csv_row_id: "row-1" });
    });

    expect(usePlaybackStore.getState().pendingSeek?.targetSec).toBe(0);
  });

  it("bumps pendingSeek.nonce on each invocation so equal targets still seek", () => {
    const setCurrentMode = vi.fn();
    const { result } = renderHook(() =>
      useOpenInAnnotateHandler({
        conceptId: 1,
        conceptKey: "k1",
        setCurrentMode,
      }),
    );

    act(() => {
      result.current("SPK_01", { start_sec: 2.0, csv_row_id: "row-1" });
    });
    const firstNonce = usePlaybackStore.getState().pendingSeek?.nonce ?? -1;

    act(() => {
      result.current("SPK_01", { start_sec: 2.0, csv_row_id: "row-1" });
    });
    const secondNonce = usePlaybackStore.getState().pendingSeek?.nonce ?? -1;

    expect(secondNonce).toBeGreaterThan(firstNonce);
  });

  it("returns a stable callback when params don't change between renders", () => {
    const setCurrentMode = vi.fn();
    const params = {
      conceptId: 5,
      conceptKey: "k5",
      setCurrentMode,
    };
    const { result, rerender } = renderHook(() =>
      useOpenInAnnotateHandler(params),
    );
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });

  it("returns a new callback when conceptId changes", () => {
    const setCurrentMode = vi.fn();
    const { result, rerender } = renderHook(
      ({ conceptId }: { conceptId: number }) =>
        useOpenInAnnotateHandler({
          conceptId,
          conceptKey: "k",
          setCurrentMode,
        }),
      { initialProps: { conceptId: 1 } },
    );
    const first = result.current;
    rerender({ conceptId: 2 });
    expect(result.current).not.toBe(first);
  });
});
