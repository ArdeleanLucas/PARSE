// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor, act, within } from "@testing-library/react";
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
let mockCurrentTime = 0;

const mockLoadConfig = vi.fn().mockResolvedValue(undefined);
const mockHydrateTags = vi.fn();
const mockSyncTagsFromServer = vi.fn().mockResolvedValue(undefined);
const mockLoadSpeaker = vi.fn().mockResolvedValue(undefined);
const mockSetInterval = vi.fn();
const mockSaveSpeaker = vi.fn().mockResolvedValue(undefined);
const mockMarkLexemeManuallyAdjusted = vi.fn();
const mockTagConcept = vi.fn();
const mockUntagConcept = vi.fn();
const mockUpdateTag = vi.fn();
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
const mockSaveEnrichments = vi.fn();
const mockReplaceEnrichments = vi.fn();
let mockEnrichmentData: Record<string, unknown> = {};
let mockChatMessages: Array<{ role: "user" | "assistant"; content: string; timestamp: string }> = [];
let mockChatSending = false;
let mockChatError: string | null = null;
let mockWaveOptions: Array<{ audioUrl?: string; onReady?: (duration: number) => void }> = [];
let mockWaveSurferInstance: unknown = null;

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
      updateTag: mockUpdateTag,
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
      histories: {},
      loadSpeaker: mockLoadSpeaker,
      setInterval: mockSetInterval,
      saveSpeaker: mockSaveSpeaker,
      markLexemeManuallyAdjusted: mockMarkLexemeManuallyAdjusted,
      moveIntervalAcrossTiers: vi.fn(),
      undo: vi.fn(),
      redo: vi.fn(),
    });
  (useAnnotationStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockAnnotationSetState(...args);
  (useAnnotationStore as unknown as { getState: () => { records: Record<string, AnnotationRecord> } }).getState = () => ({
    records: mockRecords,
  });
  return { useAnnotationStore };
});

vi.mock("./stores/playbackStore", () => {
  const usePlaybackStore = (selector: (s: unknown) => unknown) =>
    selector({
      activeSpeaker: null,
      isPlaying: false,
      currentTime: mockCurrentTime,
      duration: 4,
      selectedRegion: mockSelectedRegion,
      setSelectedRegion: mockSetSelectedRegion,
    });
  (usePlaybackStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockPlaybackSetState(...args);
  (usePlaybackStore as unknown as { getState: () => { currentTime: number } }).getState = () => ({
    currentTime: mockCurrentTime,
  });
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
      wsRef: { current: mockWaveSurferInstance },
    };
  },
}));

vi.mock("./stores/enrichmentStore", () => {
  const useEnrichmentStore = (selector: (s: unknown) => unknown) =>
    selector({
      data: mockEnrichmentData,
      loading: false,
      load: mockLoadEnrichments,
      save: mockSaveEnrichments,
      replace: mockReplaceEnrichments,
    });
  (useEnrichmentStore as unknown as { setState: (...args: unknown[]) => void }).setState = (...args: unknown[]) =>
    mockEnrichmentSetState(...args);
  // cycleSpeakerCognate / toggleSpeakerFlag read manual_overrides via
  // .getState() — provide a zustand-shaped accessor that resolves lazily
  // (not at mock-hoist time) so `mockEnrichmentData` is initialised.
  (useEnrichmentStore as unknown as {
    getState: () => {
      data: Record<string, unknown>;
      loading: boolean;
      load: () => Promise<void>;
      save: typeof mockSaveEnrichments;
      replace: typeof mockReplaceEnrichments;
    };
  }).getState = () => ({
    data: mockEnrichmentData,
    loading: false,
    load: mockLoadEnrichments,
    save: mockSaveEnrichments,
    replace: mockReplaceEnrichments,
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

// Per-test overrides for the CLEF endpoints. Defaults to "not configured"
// so the Reference Forms section stays hidden (the production gate). The
// two reference-forms tests flip these to the configured state.
let mockClefConfig: {
  configured: boolean;
  primary_contact_languages: string[];
  languages: Array<{ code: string; name: string; family?: string | null; filled?: number; total?: number }>;
  config_path: string;
  concepts_csv_exists: boolean;
  meta: Record<string, unknown>;
} = {
  configured: false,
  primary_contact_languages: [],
  languages: [],
  config_path: "",
  concepts_csv_exists: false,
  meta: {},
};
let mockCoverage: { languages: Record<string, { name: string; total: number; filled: number; empty: number; concepts: Record<string, string[]> }> } = {
  languages: {},
};

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
  detectTimestampOffset: vi.fn().mockResolvedValue({ job_id: 'offset-job-default', jobId: 'offset-job-default' }),
  detectTimestampOffsetFromPairs: vi.fn().mockResolvedValue({ job_id: 'offset-job-default', jobId: 'offset-job-default' }),
  pollOffsetDetectJob: vi.fn().mockResolvedValue({
    speaker: 'Fail01',
    offsetSec: 0.75,
    basedOn: 'automatic anchors',
    candidateCount: 3,
    protectedLexemeCount: 0,
  }),
  applyTimestampOffset: vi.fn().mockResolvedValue({ shifted: 3, protected: 0 }),
  getJobLogs: vi.fn().mockResolvedValue({ lines: [] }),
  getClefConfig: vi.fn(() => Promise.resolve(mockClefConfig)),
  getContactLexemeCoverage: vi.fn(() => Promise.resolve(mockCoverage)),
  getClefCatalog: vi.fn().mockResolvedValue({ languages: [] }),
  getClefProviders: vi.fn().mockResolvedValue({ providers: [] }),
  saveClefConfig: vi.fn().mockResolvedValue(undefined),
  startContactLexemeFetch: vi.fn().mockResolvedValue({ job_id: 'contact-fetch-job-1' }),
  listActiveJobs: vi.fn().mockResolvedValue([]),
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

function getCompareComputeModePicker() {
  const rightPanel = screen.getByTestId('right-panel');
  return within(rightPanel).getAllByRole('combobox')[1] as HTMLSelectElement;
}

async function switchCompareComputeMode(mode: 'cognates' | 'similarity' | 'contact-lexemes') {
  fireEvent.change(getCompareComputeModePicker(), { target: { value: mode } });
  await act(async () => {
    await Promise.resolve();
  });
}

function createMockWaveSurferForLanes() {
  const viewport = document.createElement("div");
  Object.defineProperty(viewport, "clientWidth", { value: 640, configurable: true });
  const wrapper = document.createElement("div");
  Object.defineProperty(wrapper, "clientWidth", { value: 640, configurable: true });
  viewport.appendChild(wrapper);

  const listeners = new Map<string, Set<(...args: unknown[]) => void>>();
  return {
    options: { minPxPerSec: 120 },
    getDuration: () => 10,
    getWrapper: () => wrapper,
    on: (event: string, handler: (...args: unknown[]) => void) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)?.add(handler);
    },
    un: (event: string, handler: (...args: unknown[]) => void) => {
      listeners.get(event)?.delete(handler);
    },
    getCurrentTime: () => 0,
  };
}

function installBlobDownloadCapture() {
  const blobs: Blob[] = [];
  const originalCreate = (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
  const originalRevoke = (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
  (URL as unknown as { createObjectURL: (blob: Blob) => string }).createObjectURL = () => "blob:mock-url";
  (URL as unknown as { revokeObjectURL: (url: string) => void }).revokeObjectURL = () => {};

  const createObjectURL = vi
    .spyOn(URL, "createObjectURL")
    .mockImplementation((value: Blob | MediaSource) => {
      if (value instanceof Blob) blobs.push(value);
      return "blob:mock-url";
    });
  const revokeObjectURL = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

  const realCreateElement = document.createElement.bind(document);
  const anchorClick = vi.fn();
  const createElement = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
    const element = realCreateElement(tag) as HTMLElement;
    if (tag === "a") {
      (element as HTMLAnchorElement).click = anchorClick;
    }
    return element;
  });

  return {
    blobs,
    anchorClick,
    createObjectURL,
    revokeObjectURL,
    restore() {
      createObjectURL.mockRestore();
      revokeObjectURL.mockRestore();
      createElement.mockRestore();
      if (originalCreate === undefined) {
        delete (URL as unknown as { createObjectURL?: unknown }).createObjectURL;
      } else {
        (URL as unknown as { createObjectURL: unknown }).createObjectURL = originalCreate;
      }
      if (originalRevoke === undefined) {
        delete (URL as unknown as { revokeObjectURL?: unknown }).revokeObjectURL;
      } else {
        (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = originalRevoke;
      }
    },
  };
}

async function readBlobText(blob: Blob): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

beforeEach(() => {
  window.localStorage.clear();
  // Default every test to "CLEF not configured" so the Reference Forms
  // gate stays closed unless the test opts into the configured state.
  mockClefConfig = {
    configured: false,
    primary_contact_languages: [],
    languages: [],
    config_path: "",
    concepts_csv_exists: false,
    meta: {},
  };
  mockCoverage = { languages: {} };
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
  mockCurrentTime = 0;
  mockChatMessages = [];
  mockChatSending = false;
  mockChatError = null;
  mockGetAuthStatus.mockResolvedValue({ authenticated: false, flow_active: false });
  mockPollAuth.mockResolvedValue({ status: "pending" });
  mockStartAuthFlow.mockResolvedValue(undefined);
  vi.mocked(apiClient.startCompute).mockResolvedValue({ job_id: 'compute-job-1', jobId: 'compute-job-1' });
  vi.mocked(apiClient.pollCompute).mockResolvedValue({ status: 'running', progress: 0 });
  vi.mocked(apiClient.getClefCatalog).mockResolvedValue({ languages: [] });
  vi.mocked(apiClient.getClefProviders).mockResolvedValue({ providers: [] });
  vi.mocked(apiClient.saveClefConfig).mockResolvedValue({
    success: true,
    config_path: 'config/sil_contact_languages.json',
    primary_contact_languages: [],
    language_count: 0,
  });
  vi.mocked(apiClient.startContactLexemeFetch).mockResolvedValue({ job_id: 'contact-fetch-job-1', jobId: 'contact-fetch-job-1' });
  vi.mocked(apiClient.listActiveJobs).mockResolvedValue([]);

  mockLoadConfig.mockClear();
  mockHydrateTags.mockClear();
  mockLoadSpeaker.mockClear();
  mockSetInterval.mockClear();
  mockSaveSpeaker.mockClear();
  mockMarkLexemeManuallyAdjusted.mockClear();
  mockTagConcept.mockClear();
  mockUpdateTag.mockClear();
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
  vi.mocked(apiClient.detectTimestampOffset).mockClear();
  vi.mocked(apiClient.detectTimestampOffsetFromPairs).mockClear();
  vi.mocked(apiClient.pollOffsetDetectJob).mockClear();
  vi.mocked(apiClient.applyTimestampOffset).mockClear();
  vi.mocked(apiClient.getJobLogs).mockClear();
  vi.mocked(apiClient.getLingPyExport).mockClear();
  vi.mocked(apiClient.saveApiKey).mockClear();
  vi.mocked(apiClient.getClefCatalog).mockClear();
  vi.mocked(apiClient.getClefProviders).mockClear();
  vi.mocked(apiClient.saveClefConfig).mockClear();
  vi.mocked(apiClient.startContactLexemeFetch).mockClear();
  vi.mocked(apiClient.listActiveJobs).mockClear();

  mockAnnotationSetState.mockClear();
  mockEnrichmentSetState.mockClear();
  mockSaveEnrichments.mockClear();
  mockReplaceEnrichments.mockClear();
  mockTagSetState.mockClear();
  mockPlaybackSetState.mockClear();
  mockConfigSetState.mockClear();
  mockWaveOptions = [];
  mockWaveSurferInstance = null;
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
    mockTags = mockTags.map((tag) =>
      tag.id === "confirmed" ? { ...tag, concepts: ["1"] } : tag,
    );

    render(<ParseUI />);

    await switchToAnnotateMode();

    expect(await screen.findByDisplayValue("aw")).toBeTruthy();
    expect(screen.getByDisplayValue("ئاو")).toBeTruthy();
    expect(screen.getByText("Annotated")).toBeTruthy();
  });

  it("switches Compare → Annotate without crashing when TranscriptionLanes initializes waveform metrics", async () => {
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    mockWaveSurferInstance = createMockWaveSurferForLanes();

    render(<ParseUI />);
    await switchToAnnotateMode();

    const latestWaveOptions = () => mockWaveOptions[mockWaveOptions.length - 1];
    await act(async () => {
      latestWaveOptions()?.onReady?.(10);
    });

    expect(await screen.findByTitle("IPA lane")).toBeTruthy();
    expect(screen.getByPlaceholderText("Enter IPA…")).toBeTruthy();
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

  it("renders compare reference forms from enrichment data", async () => {
    // Opt into CLEF-configured state so the Reference Forms section
    // actually renders. The gate hides the whole section when
    // primary_contact_languages is empty.
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar", "fa"],
      languages: [
        { code: "ar", name: "Arabic" },
        { code: "fa", name: "Persian" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    mockEnrichmentData = {
      reference_forms: {
        "1": {
          ar: { script: "ماء", ipa: "maːʔ" },
          fa: { script: "آب", ipa: "ɒːb" },
        },
      },
    };

    render(<ParseUI />);

    expect(await screen.findByText("ماء")).toBeTruthy();
    expect(screen.getByText("/maːʔ/")).toBeTruthy();
    expect(screen.getByText("آب")).toBeTruthy();
    expect(screen.getByText("/ɒːb/")).toBeTruthy();
    expect(screen.queryByText("رماد")).toBeNull();
  });

  it("shows real Arabic + Persian similarity scores from enrichment .ar/.fa fields and renders em-dash when missing", async () => {
    // Regression for a typo where persianSim was reading speakerSimilarity.tr
    // (Turkish) instead of .fa (Farsi/Persian). The backend writes under the
    // primary contact-language code -- which is "fa" for Persian -- so the
    // UI column was always 0.00 regardless of compute state.
    // Also covers the missing-score path: a speaker with no similarity entry
    // should render "—" so "not yet computed" reads differently from "0.00".
    // The column set is driven by the CLEF primary_contact_languages config
    // now, so this test seeds ar + fa explicitly.
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar", "fa"],
      languages: [
        { code: "ar", name: "Arabic" },
        { code: "fa", name: "Persian" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kzn03"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
      Kzn03: makeRecord("Kzn03", [
        { conceptText: "water", ipa: "awa", ortho: "ئاوا", start: 1, end: 2 },
      ]),
    };
    mockEnrichmentData = {
      similarity: {
        "1": {
          Fail01: {
            ar: { score: 0.42, has_reference_data: true },
            fa: { score: 0.81, has_reference_data: true },
          },
          // Kzn03 intentionally absent -- should render "—".
        },
      },
    };

    render(<ParseUI />);

    // Sanity: both speaker rows are in the DOM.
    expect(screen.getByText("/aw/")).toBeTruthy();
    expect(screen.getByText("/awa/")).toBeTruthy();
    // CLEF config loads async; wait for the dynamic headers to mount.
    await waitFor(() => expect(screen.getByTestId("sim-col-header-ar")).toBeTruthy());
    expect(screen.getByTestId("sim-col-header-fa")).toBeTruthy();
    // Fail01 row carries real values for both columns.
    expect(screen.getByText("0.42")).toBeTruthy();
    expect(screen.getByText("0.81")).toBeTruthy();
    // No row should display the silent-fallback "0.00".
    expect(screen.queryByText("0.00")).toBeNull();
    // Kzn03 row has no similarity entry -- both columns fall back to "—".
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("renders dynamic similarity columns based on CLEF primary_contact_languages (not hardcoded Arabic/Persian)", async () => {
    // Success criterion for the dynamic-primary-langs PR: when the user
    // configures English + Spanish (or any other set), the Speaker forms
    // table must render those as the similarity columns instead of the
    // built-in Arabic + Persian pair. The column data binding is driven
    // by the same primaryContactCodes list that the Reference Forms
    // cards iterate over, so there is a single source of truth for the
    // configured languages.
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["eng", "spa"],
      languages: [
        { code: "eng", name: "English" },
        { code: "spa", name: "Spanish" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01"],
      concepts: [{ id: "1", label: "water" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 1, end: 2 },
      ]),
    };
    mockEnrichmentData = {
      similarity: {
        "1": {
          Fail01: {
            eng: { score: 0.37, has_reference_data: true },
            spa: { score: 0.55, has_reference_data: true },
          },
        },
      },
    };

    render(<ParseUI />);

    await waitFor(() => expect(screen.getByTestId("sim-col-header-eng")).toBeTruthy());
    expect(screen.getByTestId("sim-col-header-eng").textContent ?? "").toMatch(/english sim\./i);
    expect(screen.getByTestId("sim-col-header-spa").textContent ?? "").toMatch(/spanish sim\./i);
    // Old hardcoded labels are gone -- regression guard so no one
    // accidentally reverts the headers.
    expect(screen.queryByTestId("sim-col-header-ar")).toBeNull();
    expect(screen.queryByTestId("sim-col-header-fa")).toBeNull();
    // Scores render under the new column codes via the dynamic cell testid.
    expect(screen.getByTestId("sim-cell-Fail01-eng").textContent ?? "").toContain("0.37");
    expect(screen.getByTestId("sim-cell-Fail01-spa").textContent ?? "").toContain("0.55");
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

  it("compare table row flag button targets a single speaker via enrichment overrides", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("speaker-flag-Fail01"));
    expect(mockUntagConcept).not.toHaveBeenCalled();
    expect(mockTagConcept).not.toHaveBeenCalledWith("problematic", "1");
    expect(mockSaveEnrichments).toHaveBeenCalledWith({
      manual_overrides: { speaker_flags: { "1": { Fail01: true } } },
    });
  });

  it("uses one shared decisions import input for the right rail and Actions menu", () => {
    render(<ParseUI />);

    const inputs = Array.from(document.querySelectorAll('input[type="file"][accept=".json"]'));
    expect(inputs).toHaveLength(1);

    const sharedInput = inputs[0] as HTMLInputElement;
    const clickSpy = vi.spyOn(sharedInput, "click");

    fireEvent.click(screen.getByRole("button", { name: "Load decisions" }));
    expect(clickSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Load Decisions" }));
    expect(clickSpy).toHaveBeenCalledTimes(2);

    clickSpy.mockRestore();
  });

  it("exports the canonical decisions payload from the Actions menu", async () => {
    mockEnrichmentData = {
      reference_forms: { "1": { ar: { script: "ماء", ipa: "maːʔ" } } },
      manual_overrides: {
        cognate_sets: { "1": { A: ["Fail01"] } },
        speaker_flags: { "1": { Fail01: true } },
        borrowing_flags: { "1": { Fail01: { decision: "borrowed", sourceLang: "ar" } } },
      },
      cognate_decisions: { "1": { decision: "split", ts: 123 } },
    };
    const capture = installBlobDownloadCapture();

    try {
      render(<ParseUI />);

      fireEvent.click(screen.getByRole("button", { name: "Actions" }));
      fireEvent.click(screen.getByRole("button", { name: "Save Decisions" }));

      expect(capture.createObjectURL).toHaveBeenCalledTimes(1);
      expect(capture.anchorClick).toHaveBeenCalledTimes(1);
      expect(capture.blobs).toHaveLength(1);

      const parsed = JSON.parse(await readBlobText(capture.blobs[0]));
      expect(parsed).toEqual({
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: { "1": { decision: "split", ts: 123 } },
          cognate_sets: { "1": { A: ["Fail01"] } },
          speaker_flags: { "1": { Fail01: true } },
          borrowing_flags: { "1": { Fail01: { decision: "borrowed", sourceLang: "ar" } } },
        },
      });
      expect(parsed).not.toHaveProperty("reference_forms");
    } finally {
      capture.restore();
    }
  });

  it("exports the canonical decisions payload from the right-rail decisions panel", async () => {
    mockEnrichmentData = {
      manual_overrides: {
        cognate_sets: { "1": { A: ["Fail01"] } },
        speaker_flags: { "1": { Fail01: true } },
        borrowing_flags: { "1": { Fail01: { decision: "uncertain", sourceLang: null } } },
        cognate_decisions: { "1": { decision: "merge", ts: 456 } },
      },
      notes: { "1": "not part of canonical decisions payload" },
    };
    const capture = installBlobDownloadCapture();

    try {
      render(<ParseUI />);

      fireEvent.click(screen.getByRole("button", { name: "Save decisions" }));

      expect(capture.createObjectURL).toHaveBeenCalledTimes(1);
      expect(capture.anchorClick).toHaveBeenCalledTimes(1);
      expect(capture.blobs).toHaveLength(1);

      const parsed = JSON.parse(await readBlobText(capture.blobs[0]));
      expect(parsed).toEqual({
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: { "1": { decision: "merge", ts: 456 } },
          cognate_sets: { "1": { A: ["Fail01"] } },
          speaker_flags: { "1": { Fail01: true } },
          borrowing_flags: { "1": { Fail01: { decision: "uncertain", sourceLang: null } } },
        },
      });
      expect(parsed).not.toHaveProperty("notes");
    } finally {
      capture.restore();
    }
  });

  it("imports the canonical decisions payload by replacing only decision categories in enrichments", async () => {
    mockEnrichmentData = {
      reference_forms: { "1": { ar: { script: "ماء", ipa: "maːʔ" } } },
      manual_overrides: { reviewer_state: { owner: "parse-builder" } },
      cognate_decisions: { "1": { decision: "accepted", ts: 111 } },
    };

    render(<ParseUI />);

    const inputs = Array.from(document.querySelectorAll('input[type="file"][accept=".json"]'));
    expect(inputs).toHaveLength(1);

    const importFile = new File(
      [JSON.stringify({
        format: "parse-decisions/v1",
        version: 1,
        manual_overrides: {
          cognate_decisions: { "2": { decision: "merge", ts: 222 } },
          cognate_sets: { "2": { B: ["Kalh01"] } },
          speaker_flags: { "2": { Kalh01: false } },
          borrowing_flags: { "2": { Kalh01: { decision: "borrowed", sourceLang: "fa" } } },
        },
      })],
      "parse-decisions.json",
      { type: "application/json" },
    );

    const sharedInput = inputs[0] as HTMLInputElement;
    Object.defineProperty(sharedInput, 'files', {
      configurable: true,
      value: [importFile],
    });
    fireEvent.change(sharedInput);

    await waitFor(() => {
      expect(mockReplaceEnrichments).toHaveBeenCalledWith({
        reference_forms: { "1": { ar: { script: "ماء", ipa: "maːʔ" } } },
        manual_overrides: {
          reviewer_state: { owner: "parse-builder" },
          cognate_decisions: { "2": { decision: "merge", ts: 222 } },
          cognate_sets: { "2": { B: ["Kalh01"] } },
          speaker_flags: { "2": { Kalh01: false } },
          borrowing_flags: { "2": { Kalh01: { decision: "borrowed", sourceLang: "fa" } } },
        },
      });
    });
  });

  it("opens the speaker import modal from the Actions menu", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Import Speaker Data…" }));

    expect(await screen.findByTestId("speaker-import")).toBeTruthy();
  });

  it("supports renaming an existing tag in Tags mode", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    fireEvent.click(await screen.findByRole("button", { name: /Tags\s*T/i }));

    const reviewButtons = await screen.findAllByRole("button", { name: /Review needed/i });
    fireEvent.click(reviewButtons[0]);
    const editButtons = screen.getAllByRole("button", { name: /Edit tag/i });
    fireEvent.click(editButtons[0]);

    const renameInput = screen.getByDisplayValue("Review needed");
    fireEvent.change(renameInput, { target: { value: "Oxford core" } });
    fireEvent.click(screen.getByRole("button", { name: /Save tag/i }));

    expect(mockUpdateTag).toHaveBeenCalledWith("review-needed", { label: "Oxford core", color: "#f59e0b" });
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

  it("shows a reference placeholder for configured languages with no data", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar", "fa"],
      languages: [
        { code: "ar", name: "Arabic" },
        { code: "fa", name: "Persian" },
      ],
      config_path: "",
      concepts_csv_exists: true,
      meta: {},
    };
    render(<ParseUI />);
    const placeholders = await screen.findAllByText("No reference data");
    expect(placeholders.length).toBeGreaterThanOrEqual(1);
  });

  it("hides the Reference Forms section entirely when CLEF is not configured", async () => {
    render(<ParseUI />);
    // Wait one tick for the mount effect's getClefConfig() to resolve,
    // then assert the section's heading and placeholder never appear.
    await screen.findByRole("button", { name: "Run" });
    expect(screen.queryByText("Reference forms")).toBeNull();
    expect(screen.queryByText("No reference data")).toBeNull();
  });

  it("opens CLEF configuration instead of starting contact-lexeme compute when the drawer Run button is unconfigured", async () => {
    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });

    await switchCompareComputeMode('contact-lexemes');
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));

    await waitFor(() => expect(apiClient.getClefCatalog).toHaveBeenCalledTimes(1));
    expect(apiClient.startCompute).not.toHaveBeenCalledWith('contact-lexemes');
    expect(apiClient.getClefProviders).toHaveBeenCalledTimes(1);
  });

  it("auto-chains similarity after a successful configured contact-lexeme populate", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ['ar', 'fa'],
      languages: [
        { code: 'ar', name: 'Arabic' },
        { code: 'fa', name: 'Persian' },
      ],
      config_path: '',
      concepts_csv_exists: true,
      meta: {},
    };
    vi.mocked(apiClient.startCompute).mockImplementation(async (computeType: string) => ({
      job_id: computeType === 'contact-lexemes' ? 'contact-job-1' : 'similarity-job-1',
      jobId: computeType === 'contact-lexemes' ? 'contact-job-1' : 'similarity-job-1',
    }));
    vi.mocked(apiClient.pollCompute).mockImplementation(async (computeType: string) => {
      if (computeType === 'contact-lexemes') {
        return {
          status: 'complete',
          progress: 100,
          result: {
            total_filled: 3,
            filled: { ar: 2, fa: 1 },
          },
        };
      }
      return { status: 'running', progress: 10 };
    });

    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });
    vi.useFakeTimers();

    await switchCompareComputeMode('contact-lexemes');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run' }));
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(apiClient.startCompute).toHaveBeenCalledWith('contact-lexemes');
    expect(apiClient.startCompute).toHaveBeenCalledWith('similarity', { speakers: ['Fail01', 'Kalh01'] });
  });

  it("does not auto-chain similarity when contact-lexeme populate completes with zero filled forms", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ['ar'],
      languages: [{ code: 'ar', name: 'Arabic' }],
      config_path: '',
      concepts_csv_exists: true,
      meta: {},
    };
    vi.mocked(apiClient.startCompute).mockResolvedValue({ job_id: 'contact-job-2', jobId: 'contact-job-2' });
    vi.mocked(apiClient.pollCompute).mockResolvedValue({
      status: 'complete',
      progress: 100,
      result: { total_filled: 0, filled: {} },
    });

    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Run' });
    vi.useFakeTimers();

    await switchCompareComputeMode('contact-lexemes');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Run' }));
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(apiClient.startCompute).toHaveBeenCalledTimes(1);
    expect(apiClient.startCompute).toHaveBeenCalledWith('contact-lexemes');
  });

  it("rehydrates in-flight contact-lexeme and similarity jobs from listActiveJobs on mount", async () => {
    vi.mocked(apiClient.listActiveJobs).mockResolvedValue([
      { jobId: 'contact-job-9', type: 'compute:contact-lexemes', status: 'running', progress: 0.25 },
      { jobId: 'similarity-job-9', type: 'compute:similarity', status: 'running', progress: 0.5 },
    ]);
    vi.mocked(apiClient.pollCompute).mockImplementation(async (computeType: string, jobId: string) => ({
      status: 'running',
      progress: jobId === 'contact-job-9' ? 25 : 50,
      message: `${computeType}:${jobId}`,
    }));

    render(<ParseUI />);

    await waitFor(() => expect(apiClient.pollCompute).toHaveBeenCalledWith('contact-lexemes', 'contact-job-9'));
    expect(apiClient.pollCompute).toHaveBeenCalledWith('similarity', 'similarity-job-9');
  });

  it("keeps Refresh as an enrichments reload instead of starting another compute job", async () => {
    render(<ParseUI />);
    await screen.findByRole('button', { name: 'Refresh' });

    mockLoadEnrichments.mockClear();
    vi.mocked(apiClient.startCompute).mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));

    await waitFor(() => expect(mockLoadEnrichments).toHaveBeenCalledTimes(1));
    expect(apiClient.startCompute).not.toHaveBeenCalled();
  });

  it("runs cognate compute on the selected compare-speaker subset", async () => {
    render(<ParseUI />);

    await screen.findByRole("button", { name: "Run" });

    fireEvent.click(screen.getByRole("button", { name: "Kalh01" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(apiClient.startCompute).toHaveBeenCalledWith("cognates", { speakers: ["Fail01"] });
    });
  });

  it("runs similarity compute on the selected compare-speaker subset", async () => {
    render(<ParseUI />);
    await screen.findByRole("button", { name: "Run" });

    const computeModeSelect = within(screen.getByTestId("right-panel")).getAllByRole("combobox")[1];
    fireEvent.change(computeModeSelect, { target: { value: "similarity" } });
    fireEvent.click(screen.getByRole("button", { name: "Kalh01" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(apiClient.startCompute).toHaveBeenCalledWith("similarity", { speakers: ["Fail01"] });
    });
  });

  it("does not start generic compare compute when no speakers remain selected", async () => {
    render(<ParseUI />);
    await screen.findByRole("button", { name: "Run" });

    const rightPanel = screen.getByTestId("right-panel");
    fireEvent.click(within(rightPanel).getByRole("button", { name: "Fail01" }));
    fireEvent.click(within(rightPanel).getByRole("button", { name: "Kalh01" }));

    expect(screen.queryByTestId('compare-compute-semantics')).toBeNull();
    expect(screen.queryByText(/Selected speakers only:/i)).toBeNull();

    const runButton = screen.getByRole("button", { name: "Run" }) as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);

    vi.mocked(apiClient.startCompute).mockClear();
    runButton.disabled = false;
    runButton.removeAttribute("disabled");
    fireEvent.click(runButton);

    expect(apiClient.startCompute).not.toHaveBeenCalled();
  });

  it("routes configured contact-lexeme Run through the isolated cross-speaker job path", async () => {
    mockClefConfig = {
      configured: true,
      primary_contact_languages: ["ar"],
      languages: [{ code: "ar", name: "Arabic" }],
      config_path: "config/sil_contact_languages.json",
      concepts_csv_exists: true,
      meta: {},
    };

    render(<ParseUI />);
    await screen.findByRole("button", { name: "Run" });

    const rightPanel = screen.getByTestId("right-panel");
    await switchCompareComputeMode('contact-lexemes');
    expect(getCompareComputeModePicker().value).toBe('contact-lexemes');
    expect(screen.getByText(/CLEF configured/i)).toBeTruthy();

    fireEvent.click(within(rightPanel).getByRole("button", { name: "Run" }));

    await waitFor(() => {
      expect(apiClient.startCompute).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(apiClient.startCompute).mock.calls[0]).toEqual(["contact-lexemes"]);
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


describe("Actions menu — transcription run flow", () => {
  // All per-model transcription actions (Normalize, STT, ORTH, IPA, and the
  // combined Full Pipeline) are now routed through a single batch runner
  // modal. The dedicated behaviours (sequential execution, pre-flight
  // preflight, step-level error capture, post-run report with tracebacks)
  // are tested in the TranscriptionRunModal / useBatchPipelineJob /
  // BatchReportModal suites. These tests just cover the entry points from
  // the action menu.

  it("Actions menu shows every transcription entry point and the cross-speaker match", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));

    expect(screen.getByText("Run Audio Normalization…")).toBeTruthy();
    expect(screen.getByText("Run STT…")).toBeTruthy();
    expect(screen.getByText("Generate ORTH (razhan)…")).toBeTruthy();
    expect(screen.getByText("Run IPA Transcription…")).toBeTruthy();
    expect(screen.getByText("Run Full Pipeline…")).toBeTruthy();
    expect(screen.getByText("Run Cross-Speaker Match")).toBeTruthy();
  });

  it("clicking a transcription action opens the run modal", async () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByTestId("actions-normalize"));

    // The modal fires getPipelineState per speaker on open; give it a
    // microtask to render.
    await act(async () => { await Promise.resolve(); });

    // The modal renders with the title supplied by the action.
    expect(screen.getByText(/Run Audio Normalization/i)).toBeTruthy();
  });

  it("opens the comments import modal from the compare right panel", () => {
    render(<ParseUI />);

    fireEvent.click(screen.getByTestId("open-comments-import"));

    expect(screen.getByTestId("comments-import")).toBeTruthy();
    expect(screen.getAllByText(/Import Audition Comments/i).length).toBeGreaterThan(1);
  });

  it("exports LingPy TSV from the compare right panel", async () => {
    const createObjectURL = vi.fn(() => "blob:lingpy");
    const revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: /Export LingPy TSV/i }));

    await waitFor(() => expect(apiClient.getLingPyExport).toHaveBeenCalledTimes(1));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:lingpy");

    clickSpy.mockRestore();
  });

  it("captures an offset anchor from annotate mode and marks the lexeme as manually adjusted", async () => {
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("annotate-capture-anchor"));

    expect(mockMarkLexemeManuallyAdjusted).toHaveBeenCalledWith("Fail01", 8, 8.4);
    expect((await screen.findByTestId("annotate-capture-toast")).textContent).toContain(
      "Anchored water @ 00:09.50 → +1.50s offset.",
    );
  });

  it("captures the current lexeme into the manual offset modal and shows the live consensus", async () => {
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset-manual"));
    expect(await screen.findByTestId("offset-manual")).toBeTruthy();

    fireEvent.click(screen.getByTestId("offset-manual-capture"));

    const anchorList = await screen.findByTestId("offset-manual-anchor-list");
    expect(within(anchorList).getByText("water")).toBeTruthy();
    expect(within(anchorList).getByText("1")).toBeTruthy();
    expect(within(anchorList).getByText("+1.50s")).toBeTruthy();
    expect(screen.getByTestId("offset-manual-consensus").textContent).toContain("+1.500 s");
    expect(mockMarkLexemeManuallyAdjusted).toHaveBeenCalledWith("Fail01", 8, 8.4);
  });

  it("shows the offset status chip and detecting modal while timestamp detection is running", async () => {
    vi.mocked(apiClient.detectTimestampOffset).mockResolvedValue({ job_id: "offset-job-1", jobId: "offset-job-1" });
    vi.mocked(apiClient.pollOffsetDetectJob).mockImplementation(
      async (_jobId, _jobType, handlers) => {
        handlers?.onProgress?.({ progress: 42, message: "Scanning anchors…" });
        return new Promise(() => {});
      },
    );

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset"));

    const statusChip = await screen.findByTestId("topbar-offset-status");
    const offsetModal = screen.getByTestId("offset-modal");
    expect(statusChip).toBeTruthy();
    expect(offsetModal).toBeTruthy();
    expect(screen.getByTestId("offset-detecting")).toBeTruthy();
    expect(within(statusChip).getByText(/Scanning anchors/i)).toBeTruthy();
    expect(within(offsetModal).getByText(/Scanning anchors/i)).toBeTruthy();
  });

  it("captures the current lexeme into the manual offset modal and shows the live consensus", async () => {
    mockCurrentTime = 9.5;
    mockRecords = {
      Fail01: makeRecord("Fail01", [
        { conceptText: "water", ipa: "aw", ortho: "ئاو", start: 8, end: 8.4 },
      ]),
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset-manual"));
    expect(await screen.findByTestId("offset-manual")).toBeTruthy();

    fireEvent.click(screen.getByTestId("offset-manual-capture"));

    const anchorList = await screen.findByTestId("offset-manual-anchor-list");
    expect(within(anchorList).getByText("water")).toBeTruthy();
    expect(within(anchorList).getByText("1")).toBeTruthy();
    expect(within(anchorList).getByText("+1.50s")).toBeTruthy();
    expect(screen.getByTestId("offset-manual-consensus").textContent).toContain("+1.500 s");
    expect(mockMarkLexemeManuallyAdjusted).toHaveBeenCalledWith("Fail01", 8, 8.4);
  });

  it("shows the offset status chip and detecting modal while timestamp detection is running", async () => {
    vi.mocked(apiClient.detectTimestampOffset).mockResolvedValue({ job_id: "offset-job-1", jobId: "offset-job-1" });
    vi.mocked(apiClient.pollOffsetDetectJob).mockImplementation(
      async (_jobId, _jobType, handlers) => {
        handlers?.onProgress?.({ progress: 42, message: "Scanning anchors…" });
        return new Promise(() => {});
      },
    );

    render(<ParseUI />);
    await switchToAnnotateMode();

    fireEvent.click(screen.getByTestId("drawer-detect-offset"));

    const statusChip = await screen.findByTestId("topbar-offset-status");
    const offsetModal = screen.getByTestId("offset-modal");
    expect(statusChip).toBeTruthy();
    expect(offsetModal).toBeTruthy();
    expect(screen.getByTestId("offset-detecting")).toBeTruthy();
    expect(within(statusChip).getByText(/Scanning anchors/i)).toBeTruthy();
    expect(within(offsetModal).getByText(/Scanning anchors/i)).toBeTruthy();
  });

  it("Reset Project resets the batch runner", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ParseUI />);

    fireEvent.click(screen.getByRole("button", { name: "Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset Project" }));

    // Batch is idle after reset → no topbar batch-status element.
    expect(screen.queryByTestId("topbar-batch-status")).toBeNull();
    expect(confirmSpy).toHaveBeenCalled();
    expect(mockAnnotationSetState).toHaveBeenCalledWith({ records: {}, dirty: {}, loading: {} });

    confirmSpy.mockRestore();
  });

  it("prefills Orthographic (Kurdish) from ortho_words word when coarse ortho is a monolithic segment", async () => {
    // Simulates the Fail102 regression: razhan produces one giant coarse
    // ortho interval covering minutes of narrative. Without ortho_words, the
    // whole paragraph text would land in the lexeme field. With ortho_words
    // (from Tier-2 forced alignment), the single-word entry wins.
    const COARSE_TEXT = "زور جوان بووین ئاو دەگڕێ";  // monolithic paragraph
    const WORD_TEXT = "ئاو";  // expected: just the Kurdish word for water

    mockConfig = {
      project_name: "PARSE",
      language_code: "ku",
      speakers: ["Fail01", "Kalh01"],
      concepts: [{ id: "1", label: "water" }, { id: "2", label: "fire" }],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };

    const base = makeRecord("Fail01", [
      { conceptText: "water", ortho: COARSE_TEXT, start: 0.0, end: 5.0 },
    ]);
    mockRecords = {
      Fail01: {
        ...base,
        tiers: {
          ...base.tiers,
          // Word-level tier: single word fully inside the concept anchor
          ortho_words: {
            name: "ortho_words",
            display_order: 4,
            intervals: [
              { start: 1.1, end: 1.4, text: WORD_TEXT },
            ],
          },
        },
      },
    };

    render(<ParseUI />);
    await switchToAnnotateMode();

    // After mode switch the annotate view renders and findAnnotationForConcept
    // preferring ortho_words populates the ortho input with the single word.
    await waitFor(() => {
      expect(screen.getByDisplayValue(WORD_TEXT)).toBeTruthy();
    });
    // The coarse paragraph must NOT appear as the pre-filled value.
    expect(screen.queryByDisplayValue(COARSE_TEXT)).toBeNull();
  });
});
