// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AnnotationRecord } from "../../api/types";

const mockGetAnnotation = vi.fn();

vi.mock("../../api/client", () => ({
  getAnnotation: (...args: unknown[]) => mockGetAnnotation(...args),
  saveAnnotation: vi.fn(),
}));

let mockActiveSpeaker: string | null = null;

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: { activeSpeaker: string | null }) => unknown) =>
    selector({ activeSpeaker: mockActiveSpeaker }),
}));

const minimalRecord: AnnotationRecord = {
  speaker: "Fail01",
  tiers: {
    ipa: { name: "ipa", display_order: 1, intervals: [] },
    ortho: { name: "ortho", display_order: 2, intervals: [] },
    concept: { name: "concept", display_order: 3, intervals: [] },
    speaker: { name: "speaker", display_order: 4, intervals: [] },
  },
  created_at: "2024-01-01T00:00:00.000Z",
  modified_at: "2024-01-01T00:00:00.000Z",
  source_wav: "Fail01.wav",
};

describe("useAnnotationSync", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockActiveSpeaker = null;
    // Reset annotation store between tests
    const { useAnnotationStore } = await import("../../stores/annotationStore");
    useAnnotationStore.setState({ records: {}, dirty: {}, loading: {} });
  });

  it("calls loadSpeaker when activeSpeaker is set", async () => {
    mockActiveSpeaker = "Fail01";
    mockGetAnnotation.mockResolvedValue(minimalRecord);

    const { useAnnotationSync } = await import("../useAnnotationSync");
    renderHook(() => useAnnotationSync());

    await waitFor(() => {
      expect(mockGetAnnotation).toHaveBeenCalledWith("Fail01");
    });
  });

  it("returns loading=true while fetch is in progress", async () => {
    mockActiveSpeaker = "Fail01";
    let resolve!: (v: AnnotationRecord) => void;
    mockGetAnnotation.mockReturnValue(
      new Promise<AnnotationRecord>((r) => {
        resolve = r;
      }),
    );

    const { useAnnotationSync } = await import("../useAnnotationSync");
    const { result } = renderHook(() => useAnnotationSync());

    await waitFor(() => {
      expect(result.current.loading).toBe(true);
    });

    resolve(minimalRecord);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });

  it("returns the record after load completes", async () => {
    mockActiveSpeaker = "Fail01";
    mockGetAnnotation.mockResolvedValue(minimalRecord);

    const { useAnnotationSync } = await import("../useAnnotationSync");
    const { result } = renderHook(() => useAnnotationSync());

    await waitFor(() => {
      expect(result.current.record).not.toBeNull();
    });

    expect(result.current.record!.speaker).toBe("Fail01");
    expect(result.current.dirty).toBe(false);
  });

  it("does not call loadSpeaker when activeSpeaker is null", async () => {
    mockActiveSpeaker = null;
    const { useAnnotationSync } = await import("../useAnnotationSync");
    renderHook(() => useAnnotationSync());

    // Give it a tick to ensure no call happens
    await new Promise((r) => setTimeout(r, 50));
    expect(mockGetAnnotation).not.toHaveBeenCalled();
  });
});
