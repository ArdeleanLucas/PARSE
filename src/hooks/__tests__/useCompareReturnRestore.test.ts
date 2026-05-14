// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";

import { useCompareReturnRestore } from "../useCompareReturnRestore";
import { useCompareReturnStore } from "../../stores/compareReturnStore";

type AppMode = "annotate" | "compare" | "tags";

describe("useCompareReturnRestore", () => {
  beforeEach(() => {
    useCompareReturnStore.getState().clear();
  });

  it("returns initialExpandedSpeaker = null when not in compare mode", () => {
    const { result } = renderHook(() =>
      useCompareReturnRestore({ currentMode: "annotate" }),
    );
    expect(result.current.initialExpandedSpeaker).toBeNull();
  });

  it("returns null when entering compare mode with no buffered snapshot", () => {
    const { result } = renderHook(() =>
      useCompareReturnRestore({ currentMode: "compare" }),
    );
    expect(result.current.initialExpandedSpeaker).toBeNull();
  });

  it("consumes a buffered snapshot on transition into compare", () => {
    const setConceptId = vi.fn();
    const setSelectedConceptKey = vi.fn();

    const { result, rerender } = renderHook(
      ({ currentMode }: { currentMode: AppMode }) =>
        useCompareReturnRestore({
          currentMode,
          setConceptId,
          setSelectedConceptKey,
        }),
      { initialProps: { currentMode: "annotate" as AppMode } },
    );

    expect(result.current.initialExpandedSpeaker).toBeNull();

    act(() => {
      useCompareReturnStore.getState().save({
        conceptId: 33,
        conceptKey: "concept-33",
        expandedSpeaker: "SPK_05",
      });
    });

    rerender({ currentMode: "compare" });

    expect(setConceptId).toHaveBeenCalledTimes(1);
    expect(setConceptId).toHaveBeenCalledWith(33);
    expect(setSelectedConceptKey).toHaveBeenCalledTimes(1);
    expect(setSelectedConceptKey).toHaveBeenCalledWith("concept-33");
    expect(result.current.initialExpandedSpeaker).toBe("SPK_05");
    // Snapshot was consumed (and cleared).
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });

  it("keeps the restored speaker across re-renders while still in compare", () => {
    const { result, rerender } = renderHook(
      ({ currentMode }: { currentMode: AppMode }) =>
        useCompareReturnRestore({ currentMode }),
      { initialProps: { currentMode: "annotate" as AppMode } },
    );

    act(() => {
      useCompareReturnStore.getState().save({
        conceptId: 1,
        conceptKey: "k1",
        expandedSpeaker: "SPK_A",
      });
    });
    rerender({ currentMode: "compare" });
    expect(result.current.initialExpandedSpeaker).toBe("SPK_A");

    // Re-render without changing mode — value persists, store stays empty.
    rerender({ currentMode: "compare" });
    expect(result.current.initialExpandedSpeaker).toBe("SPK_A");
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });

  it("resets initialExpandedSpeaker to null when leaving compare mode", () => {
    const { result, rerender } = renderHook(
      ({ currentMode }: { currentMode: AppMode }) =>
        useCompareReturnRestore({ currentMode }),
      { initialProps: { currentMode: "annotate" as AppMode } },
    );

    act(() => {
      useCompareReturnStore.getState().save({
        conceptId: 2,
        conceptKey: "k2",
        expandedSpeaker: "SPK_B",
      });
    });
    rerender({ currentMode: "compare" });
    expect(result.current.initialExpandedSpeaker).toBe("SPK_B");

    rerender({ currentMode: "tags" });
    expect(result.current.initialExpandedSpeaker).toBeNull();
  });

  it("resets when transitioning compare → annotate too", () => {
    const { result, rerender } = renderHook(
      ({ currentMode }: { currentMode: AppMode }) =>
        useCompareReturnRestore({ currentMode }),
      { initialProps: { currentMode: "annotate" as AppMode } },
    );

    act(() => {
      useCompareReturnStore.getState().save({
        conceptId: 3,
        conceptKey: "k3",
        expandedSpeaker: "SPK_C",
      });
    });
    rerender({ currentMode: "compare" });
    expect(result.current.initialExpandedSpeaker).toBe("SPK_C");

    rerender({ currentMode: "annotate" });
    expect(result.current.initialExpandedSpeaker).toBeNull();
  });

  it("does not call setConceptId / setSelectedConceptKey when they are omitted", () => {
    const { result, rerender } = renderHook(
      ({ currentMode }: { currentMode: AppMode }) =>
        useCompareReturnRestore({ currentMode }),
      { initialProps: { currentMode: "annotate" as AppMode } },
    );

    act(() => {
      useCompareReturnStore.getState().save({
        conceptId: 9,
        conceptKey: "k9",
        expandedSpeaker: "SPK_Z",
      });
    });
    expect(() => rerender({ currentMode: "compare" })).not.toThrow();
    expect(result.current.initialExpandedSpeaker).toBe("SPK_Z");
  });

  it("does not consume a snapshot saved while not in compare mode (until transition)", () => {
    const { result, rerender } = renderHook(
      ({ currentMode }: { currentMode: AppMode }) =>
        useCompareReturnRestore({ currentMode }),
      { initialProps: { currentMode: "annotate" as AppMode } },
    );

    act(() => {
      useCompareReturnStore.getState().save({
        conceptId: 4,
        conceptKey: "k4",
        expandedSpeaker: "SPK_D",
      });
    });
    // Re-render while still in annotate. The snapshot should not have been
    // consumed.
    rerender({ currentMode: "annotate" });
    expect(useCompareReturnStore.getState().snapshot).not.toBeNull();
    expect(result.current.initialExpandedSpeaker).toBeNull();

    rerender({ currentMode: "compare" });
    expect(result.current.initialExpandedSpeaker).toBe("SPK_D");
    expect(useCompareReturnStore.getState().snapshot).toBeNull();
  });
});
