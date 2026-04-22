// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, AnnotationInterval, ProjectConfig, Tag } from "./api/types";

const { mockGetAuthStatus, mockPollAuth, mockStartAuthFlow } = vi.hoisted(() => ({
  mockGetAuthStatus: vi.fn(),
  mockPollAuth: vi.fn(),
  mockStartAuthFlow: vi.fn(),
}));

let mockConfig: ProjectConfig | null = null;
let mockTags: Tag[] = [];
let mockRecords: Record<string, AnnotationRecord> = {};
let mockSelectedRegion: { start: number; end: number } | null = { start: 1.25, end: 2.5 };

const mockLoadConfig = vi.fn().mockResolvedValue(undefined);
const mockHydrateTags = vi.fn();
const mockSyncTagsFromServer = vi.fn().mockResolvedValue(undefined);
const mockLoadSpeaker = vi.fn().mockResolvedValue(undefined);
const mockSetInterval = vi.fn();
const mockSaveSpeaker = vi.fn().mockResolvedValue(undefined);
const mockTagConcept = vi.fn();
const mockUntagConcept = vi.fn();
const mockSetSelectedRegion = vi.fn();
const mockSetActiveSpeaker = vi.fn();
const mockSetActiveConcept = vi.fn();
const mockSetSelectedSpeakers = vi.fn();
const mockChatSend = vi.fn();
const mockPlayPause = vi.fn();
const mockSkip = vi.fn();
const mockSeek = vi.fn();
const mockAddRegion = vi.fn();
const mockScrollToTimeAtFraction = vi.fn();
const mockSetWaveZoom = vi.fn();
const mockSetRate = vi.fn();
const mockAnnotationSetState = vi.fn();
const mockEnrichmentSetState = vi.fn();
const mockTagSetState = vi.fn();
const mockPlaybackSetState = vi.fn();
const mockConfigSetState = vi.fn();
const mockLoadEnrichments = vi.fn().mockResolvedValue(undefined);
let mockEnrichmentData: Record<string, unknown> = {};
let mockChatMessages: Array<{ role: "user" | "assistant"; content: string; timestamp: string }> = [];
let mockChatSending = false;
let mockChatError: string | null = null;
let mockWaveOptions: Array<{ audioUrl?: string; onReady?: (duration: number) => void }> = [];

vi.mock("./stores/configStore", () => {
  const useConfigStore = (selector: (s: unknown) => unknown) =>
    selector({ config: mockConfig, load: mockLoadConfig });
  (useConfigStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockConfigSetState(...args);
  return { useConfigStore };
});

vi.mock("./stores/tagStore", () => {
  const useTagStore = (selector: (s: unknown) => unknown) =>
    selector({
      tags: mockTags,
      hydrate: mockHydrateTags,
      syncFromServer: mockSyncTagsFromServer,
      tagConcept: mockTagConcept,
      untagConcept: mockUntagConcept,
      getTagsForConcept: (conceptId: string) => mockTags.filter((tag) => tag.concepts.includes(conceptId)),
    });
  (useTagStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockTagSetState(...args);
  return { useTagStore };
});

vi.mock("./stores/annotationStore", () => {
  const useAnnotationStore = (selector: (s: unknown) => unknown) =>
    selector({
      records: mockRecords,
      loadSpeaker: mockLoadSpeaker,
      setInterval: mockSetInterval,
      saveSpeaker: mockSaveSpeaker,
    });
  (useAnnotationStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockAnnotationSetState(...args);
  return { useAnnotationStore };
});

vi.mock("./stores/playbackStore", () => {
  const usePlaybackStore = (selector: (s: unknown) => unknown) =>
    selector({
      activeSpeaker: null,
      isPlaying: false,
      currentTime: 0,
      duration: 4,
      selectedRegion: mockSelectedRegion,
      setSelectedRegion: mockSetSelectedRegion,
    });
  (usePlaybackStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockPlaybackSetState(...args);
  return { usePlaybackStore };
});

vi.mock("./hooks/useChatSession", () => ({
  useChatSession: () => ({
    messages: mockChatMessages,
    sessionId: "test-session",
    sending: mockChatSending,
    error: mockChatError,
    send: mockChatSend,
    clear: vi.fn(),
  }),
}));

vi.mock("./hooks/useWaveSurfer", () => ({
  useWaveSurfer: (options: { audioUrl?: string; onReady?: (duration: number) => void }) => {
    mockWaveOptions.push(options);
    return {
      playPause: mockPlayPause,
      seek: mockSeek,
      scrollToTimeAtFraction: mockScrollToTimeAtFraction,
      skip: mockSkip,
      addRegion: mockAddRegion,
      setZoom: mockSetWaveZoom,
      setRate: mockSetRate,
      wsRef: { current: null },
    };
  },
}));

vi.mock("./stores/enrichmentStore", () => {
  const useEnrichmentStore = (selector: (s: unknown) => unknown) =>
    selector({ data: mockEnrichmentData, loading: false, load: mockLoadEnrichments, save: vi.fn() });
  (useEnrichmentStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockEnrichmentSetState(...args);
  // cycleSpeakerCognate / toggleSpeakerFlag read manual_overrides via
  // .getState() — provide a zustand-shaped accessor that resolves lazily
  // (not at mock-hoist time) so `mockEnrichmentData` is initialised.
  (useEnrichmentStore as unknown as { getState: () => unknown }).getState = () => ({
    data: mockEnrichmentData,
    loading: false,
    load: vi.fn(),
    save: vi.fn(),
  });
  return { useEnrichmentStore };
});

vi.mock("./stores/uiStore", () => ({
  useUIStore: (selector: (s: unknown) => unknown) =>
    selector({
      setActiveSpeaker: mockSetActiveSpeaker,
      setActiveConcept: mockSetActiveConcept,
      setSelectedSpeakers: mockSetSelectedSpeakers,
    }),
}));

vi.mock("./api/client", () => ({
  getLingPyExport: vi.fn().mockResolvedValue(''),
  saveApiKey: vi.fn().mockResolvedValue(undefined),
  getAuthStatus: mockGetAuthStatus,
  pollAuth: mockPollAuth,
  startAuthFlow: mockStartAuthFlow,
  startSTT: vi.fn().mockResolvedValue({ job_id: 'stt-job-1' }),
  startCompute: vi.fn().mockResolvedValue({ job_id: 'compute-job-1' }),
  startNormalize: vi.fn().mockResolvedValue({ job_id: 'normalize-job-1' }),
  pollSTT: vi.fn().mockResolvedValue({ status: 'running', progress: 0 }),
  pollNormalize: vi.fn().mockResolvedValue({ status: 'running', progress: 0 }),
  pollCompute: vi.fn().mockResolvedValue({ status: 'running', progress: 0 }),
}));

import { ParseUI } from "./ParseUI";
import * as apiClient from "./api/client";

function makeRecord(
  speaker: string,
  concepts: Array<{ conceptText: string; ipa?: string; ortho?: string; start: number; end: number }>,
): AnnotationRecord {
  const tier = (intervals: AnnotationInterval[]) => ({
    name: "tier",
    display_order: 1,
    intervals,
  });

  return {
    speaker,
    tiers: {
      ipa: tier(concepts.filter((c) => c.ipa != null).map((c) => ({ start: c.start, end: c.end, text: c.ipa ?? "" }))),
      ortho: tier(concepts.filter((c) => c.ortho != null).map((c) => ({ start: c.start, end: c.end, text: c.ortho ?? "" }))),
      concept: {
        name: "concept",
        display_order: 3,
        intervals: concepts.map((c) => ({ start: c.start, end: c.end, text: c.conceptText })),
      },
      speaker: { name: "speaker", display_order: 4, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    source_wav: `${speaker}.wav`,
  };
}

async function switchToAnnotateMode() {
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  fireEvent.click(await screen.findByRole("button", { name: /Annotate\s*A/i }));
}

beforeEach(() => {
  window.localStorage.clear();
  mockConfig = {
    project_name: "PARSE",
    language_code: "ku",
    speakers: ["Fail01", "Kalh01"],
    concepts: [
      { id: "1", label: "water" },
      { id: "2", label: "fire" },
    ],
    audio_dir: "audio",
    annotations_dir: "annotations",
  };
  mockTags = [
    { id: "review-needed", label: "Review needed", color: "#f59e0b", concepts: [] },
    { id: "confirmed", label: "Confirmed", color: "#10b981", concepts: [] },
    { id: "problematic", label: "Problematic", color: "#ef4444", concepts: [] },
  ];
  mockRecords = {};
  mockEnrichmentData = {};
  mockSelectedRegion = { start: 1.25, end: 2.5 };
  mockChatMessages = [];
  mockChatSending = false;
  mockChatError = null;
  mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
  mockPollAuth.mockResolvedValue({ status: "pending" });
  mockStartAuthFlow.mockResolvedValue(undefined);

  mockLoadConfig.mockClear();
  mockHydrateTags.mockClear();
  mockLoadSpeaker.mockClear();
  mockSetInterval.mockClear();
  mockSaveSpeaker.mockClear();
  mockTagConcept.mockClear();
  mockUntagConcept.mockClear();
  mockSetSelectedRegion.mockClear();
  mockSetActiveSpeaker.mockClear();
  mockSetActiveConcept.mockClear();
  mockSetSelectedSpeakers.mockClear();
  mockChatSend.mockClear();
  mockPlayPause.mockClear();
  mockSkip.mockClear();
  mockSeek.mockClear();
  mockAddRegion.mockClear();
  mockScrollToTimeAtFraction.mockClear();
  mockSetWaveZoom.mockClear();
  mockSetRate.mockClear();
  mockGetAuthStatus.mockClear();
  mockPollAuth.mockClear();
  mockStartAuthFlow.mockClear();
  vi.mocked(apiClient.startNormalize).mockClear();
  vi.mocked(apiClient.pollNormalize).mockClear();
  vi.mocked(apiClient.startSTT).mockClear();
  vi.mocked(apiClient.pollSTT).mockClear();
  vi.mocked(apiClient.startCompute).mockClear();
  vi.mocked(apiClient.pollCompute).mockClear();
  vi.mocked(apiClient.getLingPyExport).mockClear();
  vi.mocked(apiClient.saveApiKey).mockClear();
  mockAnnotationSetState.mockClear();
  mockEnrichmentSetState.mockClear();
  mockTagSetState.mockClear();
  mockPlaybackSetState.mockClear();
  mockConfigSetState.mockClear();
  mockWaveOptions = [];
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ParseUI", () => {
  it("loads config and tag hydration on mount and computes reviewed count from confirmed tags", () => {
    mockTags = mockTags.map((tag) =>
      tag.id === "confirmed" ? { ...tag, concepts: ["1"] } : tag,
    );

    render(<ParseUI />);

    expect(mockLoadConfig).toHaveBeenCalledOnce();
    expect(mockHydrateTags).toHaveBeenCalledOnce();
    expect(mockSyncTagsFromServer).toHaveBeenCalledOnce();
    expect(screen.getByText("1 / 2 reviewed")).toBeTruthy();
  });

  it("pre-populates annotate fields from stored intervals and shows Annotated badge", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    expect(await screen.findByDisplayValue("aw")).toBeTruthy();
    expect(screen.getByDisplayValue("ئاو")).toBeTruthy();
    expect(screen.getByText("Annotated")).toBeTruthy();
  });

  it("saves annotation tiers for the selected region and persists the speaker record", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", []),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.change(screen.getByPlaceholderText("Enter IPA…"), { target: { value: "aβ" } });
    fireEvent.change(screen.getByPlaceholderText("Enter orthographic form…"), { target: { value: "ئاو" } });
    fireEvent.click(screen.getAllByRole("button", { name: /Save Annotation/i })[0]);

    expect(mockSetInterval).toHaveBeenCalledWith("Fail01", "ipa", {
      start: 1.25,
      end: 2.5,
      text: "aβ",
    });
    expect(mockSetInterval).toHaveBeenCalledWith("Fail01", "ortho", {
      start: 1.25,
      end: 2.5,
      text: "ئاو",
    });
    expect(mockSetInterval).toHaveBeenCalledWith("Fail01", "concept", {
      start: 1.25,
      end: 2.5,
      text: "water",
    });
    await waitFor(() => expect(mockSaveSpeaker).toHaveBeenCalledWith("Fail01"));
  });

  it("marks the current concept confirmed from annotate mode", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", []),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByRole("button", { name: /Mark Done/i }));
    expect(mockTagConcept).toHaveBeenCalledWith("confirmed", "1");
  });

  it("waits for the newly selected speaker audio to become ready before seeking and drawing a region", async () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Fail02"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
      Fail02: makeRecord("Fail02", [
        { conceptText: "water", ipa: "aβ", ortho: "ئاڤ", start: 5, end: 6 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    const latestWaveOptions = () => mockWaveOptions[mockWaveOptions.length - 1];

    expect(latestWaveOptions()?.audioUrl).toBe("/Fail01.wav");

    await act(async () => {
      latestWaveOptions()?.onReady?.(10);
    });

    expect(mockSeek).toHaveBeenCalledWith(1);
    expect(mockAddRegion).toHaveBeenCalledWith(1, 2);

    mockSeek.mockClear();
    mockAddRegion.mockClear();
    mockScrollToTimeAtFraction.mockClear();

    fireEvent.click(screen.getAllByRole("button", { name: "Fail02" })[0]);

    await waitFor(() => expect(latestWaveOptions()?.audioUrl).toBe("/Fail02.wav"));
    expect(mockSeek).not.toHaveBeenCalled();
    expect(mockAddRegion).not.toHaveBeenCalled();
    expect(mockScrollToTimeAtFraction).not.toHaveBeenCalled();

    await act(async () => {
      latestWaveOptions()?.onReady?.(12);
    });

    expect(mockSeek).toHaveBeenCalledWith(5);
    expect(mockAddRegion).toHaveBeenCalledWith(5, 6);
    expect(mockScrollToTimeAtFraction).toHaveBeenCalledWith(5, 0.33);
  });

  it("renders compare reference forms from enrichment data", () => {
    mockEnrichmentData = {
      reference_forms: {
        "1": {
          ar: { script: "ماء", ipa: "maːʔ" },
          fa: { script: "آب", ipa: "ɒːb" },
        },
      },
    };

    render(<ParseUI />);

    expect(screen.getByText("ماء")).toBeTruthy();
    expect(screen.getByText("/maːʔ/")).toBeTruthy();
    expect(screen.getByText("آب")).toBeTruthy();
    expect(screen.getByText("/ɒːb/")).toBeTruthy();
    expect(screen.queryByText("رماد")).toBeNull();
  });

  it("renders compare speaker forms from annotation data instead of MOCK_FORMS placeholders", () => {
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kzn03"],
      concepts: [
        { id: "1", label: "water" },
        { id: "2", label: "fire" },
      ],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
        { conceptText: "water", ipa: "aːw", ortho: "ئاو", start: 3, end: 4 },
      ]),
      Kzn03: makeRecord("Kzn03", [
        { conceptText: "water", ipa: "awa", ortho: "ئاوا", start: 1, end: 2 },
      ]),
    };

    render(<ParseUI />);

    expect(screen.getByText("/aw/")).toBeTruthy();
    expect(screen.getByText("/awa/")).toBeTruthy();
    expect(screen.getByText("2 utterances")).toBeTruthy();
    expect(screen.queryByText("/ramaːd/")).toBeNull();
  });

  it("wires compare Flag and Accept concept buttons to tag actions", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: /^Flag$/i }));
    fireEvent.click(screen.getByRole("button", { name: /Accept concept/i }));

    expect(mockTagConcept).toHaveBeenCalledWith("problematic", "1");
    expect(mockTagConcept).toHaveBeenCalledWith("confirmed", "1");
  });

  it("compare table row flag button targets a single speaker (not the whole concept)", () => {
    // The flag button now writes per-speaker state to
    // `manual_overrides.speaker_flags[concept][speaker]` via the enrichment
    // store, rather than toggling the concept-wide `problematic` tag. That
    // change means flagging Fail01 must NOT pull the whole concept into the
    // Flagged tab — only Fail01 shows as amber.
    render(<ParseUI />);

    fireEvent.click(screen.getByTitle("Toggle flag for Fail01"));
    expect(mockUntagConcept).not.toHaveBeenCalled();
    expect(mockTagConcept).not.toHaveBeenCalledWith("problematic", "1");
  });

  it("opens the speaker import modal from the Actions menu", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Import Speaker Data…" }));

    expect(await screen.findByTestId("speaker-import")).toBeTruthy();
  });

  it("renames the mode menu label to Tags", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByRole("button", { name: /Tags\s*T/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Manage Tags" })).toBeNull();
  });

  it("shows PARSE as the top-left title", () => {
    render(<ParseUI />);

    expect(screen.getByText("PARSE")).toBeTruthy();
    expect(screen.queryByText("PARSE Compare")).toBeNull();
  });

  it("shows inline arrow hotkeys on annotate prev/next buttons", async () => {
    render(<ParseUI />);
    await switchToAnnotateMode();

    expect(screen.getByRole("button", { name: /←\s*Prev/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Next\s*→/i })).toBeTruthy();
  });

  it("shows mode hotkeys inside the mode dropdown", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByRole("button", { name: /Annotate\s*A/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Compare\s*C/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Tags\s*T/i })).toBeTruthy();
  });

  it("supports app-mode hotkeys a/c/t", async () => {
    render(<ParseUI />);

    fireEvent.keyDown(window, { key: "a" });
    expect(await screen.findByRole("button", { name: /Mark Done/i })).toBeTruthy();

    fireEvent.keyDown(window, { key: "t" });
    expect(await screen.findByText("Linguistic tags")).toBeTruthy();

    fireEvent.keyDown(window, { key: "c" });
    expect(await screen.findByRole("button", { name: /Accept concept/i })).toBeTruthy();
  });

  it("uses arrow keys to change concepts in annotate mode", async () => {
    render(<ParseUI />);
    await switchToAnnotateMode();

    expect(screen.getByRole("heading", { name: "water" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByRole("heading", { name: "fire" })).toBeTruthy();

    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(await screen.findByRole("heading", { name: "water" })).toBeTruthy();
  });

  it("persists compare notes per concept via localStorage on blur", () => {
    const { unmount } = render(<ParseUI />);
    const notesField = screen.getByPlaceholderText(/Add observations, etymological notes, or questions for review/i);

    fireEvent.change(notesField, { target: { value: "Loanword candidate from Arabic." } });
    fireEvent.blur(notesField);
    unmount();

    render(<ParseUI />);
    expect(screen.getByDisplayValue("Loanword candidate from Arabic.")).toBeTruthy();
  });

  it("renders assistant markdown with readable headings, lists, and inline code in the AI chat panel", async () => {
    mockGetAuthStatus.mockResolvedValue({ authenticated: true, provider: "openai", method: "api_key", flow_active: false });
    mockChatMessages = [
      {
        role: "assistant",
        timestamp: "2026-04-21T12:00:00.000Z",
        content:
          "**Cannot import speakers — read-only MVP constraints.** ### What I checked - `project_context_read`: Current project has 0 speakers. - `read_text_preview`: File not found. ### Recommended next steps 1. Add speaker audio files. 2. Create initial annotation files.",
      },
    ];

    render(<ParseUI />);

    fireEvent.focus(screen.getByPlaceholderText(/Ask PARSE AI about water/i));

    expect(await screen.findByRole("heading", { name: "What I checked" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Recommended next steps" })).toBeTruthy();
    expect(screen.getByText("project_context_read").tagName).toBe("CODE");
    expect(screen.getByText(/read-only MVP constraints\./i).closest("strong")).not.toBeNull();
    expect(screen.queryByText(/\*\*Cannot import speakers/i)).toBeNull();
  });

  it("shows a reference placeholder when enrichmentStore has no reference forms", () => {
    render(<ParseUI />);
    expect(screen.getAllByText("No reference data").length).toBeGreaterThanOrEqual(1);
  });

  it("restores the xAI provider badge after reload when backend reports provider=xai", async () => {
    // Regression: the mount effect used to call setProvider('openai')
    // unconditionally whenever the backend said authenticated=true, so users
    // who saved an xAI key would see the OpenAI badge on reload.
    mockGetAuthStatus.mockResolvedValue({
      authenticated: true,
      provider: "xai",
      method: "api_key",
      flow_active: false,
    });

    render(<ParseUI />);

    // Expand the minimized AI chat so the provider badge renders.
    fireEvent.focus(screen.getByPlaceholderText(/Ask PARSE AI about water/i));

    expect(await screen.findByText("Connected to xAI")).toBeTruthy();
    expect(screen.getByText(/grok-4\.2 reasoning/i)).toBeTruthy();
    expect(screen.queryByText("Connected to OpenAI")).toBeNull();
  });

  it("restores the OpenAI provider badge after reload when backend reports provider=openai", async () => {
    mockGetAuthStatus.mockResolvedValue({
      authenticated: true,
      provider: "openai",
      method: "api_key",
      flow_active: false,
    });

    render(<ParseUI />);

    fireEvent.focus(screen.getByPlaceholderText(/Ask PARSE AI about water/i));

    expect(await screen.findByText("Connected to OpenAI")).toBeTruthy();
    expect(screen.getByText("gpt-5.4")).toBeTruthy();
    expect(screen.queryByText("Connected to xAI")).toBeNull();
  });
});


describe("Actions menu job lifecycle", () => {
  it("Actions menu renders all 5 processing action buttons", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    expect(screen.getByText("Run Audio Normalization")).toBeTruthy();
    expect(screen.getByText("Run Orthographic STT")).toBeTruthy();
    expect(screen.getByText("Run IPA Transcription")).toBeTruthy();
    expect(screen.getByText("Run Full Pipeline")).toBeTruthy();
    expect(screen.getByText("Run Cross-Speaker Match")).toBeTruthy();
  });

  it("shows topbar normalize progress and disables the button while running", async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.startNormalize).mockResolvedValue({ job_id: "normalize-1" });
    vi.mocked(apiClient.pollNormalize).mockResolvedValue({ status: "running", progress: 25, segments: [] });

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run Audio Normalization" }));
      await Promise.resolve();
    });

    expect(apiClient.startNormalize).toHaveBeenCalledWith("Fail01");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByTestId("topbar-action-statuses")).toBeTruthy();
    expect(screen.getByText("Normalizing audio…")).toBeTruthy();
    expect(screen.getByText("25%")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect((screen.getByRole("button", { name: "Normalizing…" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("action buttons have disabled class when applicable", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    const normalizeButton = screen.getByRole("button", { name: "Run Audio Normalization" });

    expect(normalizeButton.className).toContain("disabled:opacity-50");
    expect(normalizeButton.className).toContain("disabled:cursor-not-allowed");
  });

  it("shows retry for action errors and reruns the job", async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.startNormalize)
      .mockResolvedValueOnce({ job_id: "normalize-error-1" })
      .mockResolvedValueOnce({ job_id: "normalize-error-2" });
    vi.mocked(apiClient.pollNormalize)
      .mockResolvedValueOnce({ status: "error", progress: 40, segments: [], message: "Normalize failed" } as unknown as Awaited<ReturnType<typeof apiClient.pollNormalize>>)
      .mockResolvedValue({ status: "running", progress: 60, segments: [] });

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run Audio Normalization" }));
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByText("Normalize failed")).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      await Promise.resolve();
    });

    expect(apiClient.startNormalize).toHaveBeenCalledTimes(2);
  });

  it("Reset Project clears action job states", async () => {
    vi.useFakeTimers();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(apiClient.startNormalize).mockResolvedValue({ job_id: "normalize-reset" });
    vi.mocked(apiClient.pollNormalize).mockResolvedValue({ status: "running", progress: 10, segments: [] });

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Run Audio Normalization" }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByTestId("topbar-action-statuses")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset Project" }));

    expect(screen.queryByTestId("topbar-action-statuses")).toBeNull();
    expect(confirmSpy).toHaveBeenCalled();
    expect(mockAnnotationSetState).toHaveBeenCalledWith({ records: {}, dirty: {}, loading: {} });
    expect(mockEnrichmentSetState).toHaveBeenCalledWith({ data: {}, loading: false });
    expect(mockTagSetState).toHaveBeenCalledWith({ tags: [] });
    expect(mockPlaybackSetState).toHaveBeenCalledWith({ activeSpeaker: null, currentTime: 0 });
    expect(mockConfigSetState).toHaveBeenCalledWith({ config: null, loading: false });

    confirmSpy.mockRestore();
  });
});
