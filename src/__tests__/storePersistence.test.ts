// src/__tests__/storePersistence.test.ts
import { describe, it, expect, beforeEach, vi } from "vitest";

// Mock API client so tests don't need a live server
vi.mock("../api/client", () => ({
  getConfig: vi.fn(),
  getAnnotation: vi.fn(),
  saveAnnotation: vi.fn(),
  getEnrichments: vi.fn(),
  saveEnrichments: vi.fn(),
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

  it("tagStore tags survive navigation to compare and back", () => {
    // Add a tag to tagStore
    const { addTag } = useTagStore.getState();
    addTag("TestTag", "#ff0000");

    // Simulate "navigating away" by just reading from fresh state access
    const tags = useTagStore.getState().tags;
    expect(tags).toHaveLength(1);
    expect(tags[0].label).toBe("TestTag");

    // Verify concept assignment survives
    const tagId = tags[0].id;
    useTagStore.getState().tagConcept(tagId, "water");
    const conceptTags = useTagStore.getState().getTagsForConcept("water");
    expect(conceptTags.some((t) => t.id === tagId)).toBe(true);
  });

  it("configStore does not re-fetch if already loaded", async () => {
    const mockConfig = {
      project_name: "TestProject",
      language_code: "kmr",
      speakers: ["Fail01"],
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
