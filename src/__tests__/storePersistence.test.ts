// src/__tests__/storePersistence.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock API client so tests don't need a live server
const mockGetAnnotation = vi.fn();
const mockSaveAnnotation = vi.fn();
const mockPutTags = vi.fn().mockResolvedValue(undefined);

vi.mock("../api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: (...args: unknown[]) => mockGetAnnotation(...args),
  saveAnnotation: (...args: unknown[]) => mockSaveAnnotation(...args),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
  putTags: (...args: unknown[]) => mockPutTags(...args),
}));

vi.mock("@/api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: (...args: unknown[]) => mockGetAnnotation(...args),
  saveAnnotation: (...args: unknown[]) => mockSaveAnnotation(...args),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
  putTags: (...args: unknown[]) => mockPutTags(...args),
}));

// Must import stores AFTER mock is declared
import { useAnnotationStore } from "../stores/annotationStore";
import { useTagStore } from "../stores/tagStore";
import { useConfigStore } from "../stores/configStore";
import { usePlaybackStore } from "../stores/playbackStore";
import { getConfig } from "../api/client";

const mockedGetConfig = vi.mocked(getConfig);

describe("Cross-session persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset stores to initial state
    useAnnotationStore.setState({ records: {}, loading: {}, dirty: {} });
    useTagStore.setState({ tags: [] });
    useConfigStore.setState({ config: null, loading: false });
    usePlaybackStore.setState({ activeSpeaker: null, currentTime: 0 });
  });

  it("annotationStore dirty intervals survive component remount", () => {
    // Simulate setting dirty state (as AnnotationPanel would do)
    useAnnotationStore.setState({
      records: {
        Fail01: {
          speaker: "Fail01",
          tiers: {
            ipa: { name: "ipa", display_order: 1, intervals: [{ start: 0.1, end: 0.5, text: "test" }] },
          },
          created_at: "2026-01-01T00:00:00Z",
          modified_at: "2026-01-01T00:00:00Z",
          source_wav: "Fail01.wav",
        },
      },
      dirty: { Fail01: true },
      loading: {},
    });

    // Zustand stores are module singletons — simulate remount by re-reading state
    const state = useAnnotationStore.getState();
    expect(state.records["Fail01"]).toBeDefined();
    expect(state.dirty["Fail01"]).toBe(true);
    expect(state.records["Fail01"].tiers.ipa.intervals[0].text).toBe("test");
  });

  it("tagStore vocabulary survives navigation to compare and back", () => {
    // Add a tag to tagStore
    const { addTag } = useTagStore.getState();
    addTag("TestTag", "#ff0000");

    // Simulate "navigating away" by just reading from fresh state access
    const tags = useTagStore.getState().tags;
    expect(tags).toHaveLength(1);
    expect(tags[0].label).toBe("TestTag");
    expect(tags[0]).not.toHaveProperty("concepts");
  });

  it("configStore does not re-fetch if already loaded", async () => {
    const mockConfig = {
      project_name: "TestProject",
      language_code: "kmr",
      speakers: ["Fail01"],
      concepts: [],
      audio_dir: "/audio",
      annotations_dir: "/annotations",
    };
    mockedGetConfig.mockResolvedValueOnce(mockConfig);

    // First load — should call API
    await useConfigStore.getState().load();
    expect(mockedGetConfig).toHaveBeenCalledTimes(1);
    expect(useConfigStore.getState().config?.project_name).toBe("TestProject");

    // Second load — should NOT call API (idempotent)
    await useConfigStore.getState().load();
    expect(mockedGetConfig).toHaveBeenCalledTimes(1); // still 1
  });

  it("playbackStore resets currentTime to 0 when activeSpeaker changes", () => {
    // Set up initial state with a currentTime
    usePlaybackStore.setState({ activeSpeaker: "Fail01", currentTime: 3.7 });

    // Change speaker
    usePlaybackStore.getState().setActiveSpeaker("Mand01");

    const state = usePlaybackStore.getState();
    expect(state.activeSpeaker).toBe("Mand01");
    expect(state.currentTime).toBe(0); // must reset to 0
  });
});


describe("annotationStore.saveSpeaker server round-trip", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAnnotationStore.setState({ records: {}, loading: {}, dirty: {}, histories: {} });
  });

  it("overwrites the local record with the full normalized annotation returned by the server", async () => {
    const before = {
      speaker: "Fail01",
      source_wav: "Fail01.wav",
      tiers: {
        concept: { name: "concept", display_order: 1, intervals: [{ start: 1, end: 2, text: "water" }] },
        ipa: { name: "ipa", display_order: 2, intervals: [{ start: 1, end: 2, text: "old-ipa" }] },
        ortho: { name: "ortho", display_order: 3, intervals: [{ start: 1, end: 2, text: "old-ortho" }] },
        ortho_words: { name: "ortho_words", display_order: 4, intervals: [{ start: 1, end: 1.5, text: "old" }] },
      },
      created_at: "2026-01-01T00:00:00Z",
      modified_at: "2026-01-01T00:00:00Z",
    };
    const normalized = {
      ...before,
      tiers: {
        concept: { name: "concept", display_order: 1, intervals: [{ start: 1.1, end: 2.1, text: "water" }] },
        ipa: { name: "ipa", display_order: 2, intervals: [{ start: 1.1, end: 2.1, text: "new-ipa" }] },
        ortho: { name: "ortho", display_order: 3, intervals: [{ start: 1.1, end: 2.1, text: "new-ortho" }] },
        ortho_words: { name: "ortho_words", display_order: 4, intervals: [{ start: 1.1, end: 1.6, text: "new" }] },
      },
      modified_at: "2026-01-01T00:00:01Z",
    };
    useAnnotationStore.setState({ records: { Fail01: before }, dirty: { Fail01: true } });
    mockSaveAnnotation.mockResolvedValueOnce(normalized);

    const result = await useAnnotationStore.getState().saveSpeaker("Fail01", before);

    expect(result.record).toMatchObject(normalized);
    expect(result.changedTiers).toEqual(["concept", "ipa", "ortho", "ortho_words"]);
    expect(useAnnotationStore.getState().records.Fail01).toBe(result.record);
    expect(useAnnotationStore.getState().dirty.Fail01).toBe(false);
  });
});
