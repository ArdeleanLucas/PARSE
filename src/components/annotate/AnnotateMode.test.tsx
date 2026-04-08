// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AnnotateMode } from "./AnnotateMode";

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

// --- configStore ---
let mockConfig: {
  project_name: string;
  language_code: string;
  speakers: string[];
  audio_dir: string;
  annotations_dir: string;
} | null = null;

const mockLoad = vi.fn();

vi.mock("../../stores/configStore", () => ({
  useConfigStore: (selector: (s: { config: typeof mockConfig; load: typeof mockLoad }) => unknown) =>
    selector({ config: mockConfig, load: mockLoad }),
}));

// --- uiStore ---
let mockUIState = {
  activeSpeaker: null as string | null,
  activeConcept: null as string | null,
  annotatePanel: "annotation" as "annotation" | "transcript" | "suggestions" | "chat",
  onboardingComplete: true,
  setActiveSpeaker: vi.fn(),
  setActiveConcept: vi.fn(),
  setAnnotatePanel: vi.fn(),
  setOnboardingComplete: vi.fn(),
};

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: typeof mockUIState) => unknown) => selector(mockUIState),
}));

// --- playbackStore ---
const mockPlaybackState = {
  activeSpeaker: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  zoom: 100,
  playbackRate: 1,
  loopEnabled: false,
  selectedRegion: null,
  setActiveSpeaker: vi.fn(),
  setZoom: vi.fn(),
  setPlaybackRate: vi.fn(),
  toggleLoop: vi.fn(),
};

vi.mock("../../stores/playbackStore", () => ({
  usePlaybackStore: Object.assign(
    (selector: (s: typeof mockPlaybackState) => unknown) => selector(mockPlaybackState),
    { setState: vi.fn() },
  ),
}));

// --- annotationStore ---
let mockDirty: Record<string, boolean> = {};

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (s: { dirty: Record<string, boolean> }) => unknown) =>
    selector({ dirty: mockDirty }),
}));

// --- hooks ---
vi.mock("../../hooks/useWaveSurfer", () => ({
  useWaveSurfer: () => ({
    play: vi.fn(),
    pause: vi.fn(),
    playPause: vi.fn(),
    seek: vi.fn(),
    skip: vi.fn(),
    jump: vi.fn(),
    setZoom: vi.fn(),
    setRate: vi.fn(),
    addRegion: vi.fn(),
    clearRegions: vi.fn(),
    playRegion: vi.fn(),
    wsRef: { current: null },
    regionsRef: { current: null },
  }),
}));

vi.mock("../../hooks/useAnnotationSync", () => ({
  useAnnotationSync: () => ({ record: null, dirty: false, loading: false, activeSpeaker: null }),
}));

// --- child components (stubs) ---
vi.mock("./OnboardingFlow", () => ({
  OnboardingFlow: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="onboarding-flow">
      <button onClick={onComplete}>Complete Onboarding</button>
    </div>
  ),
}));

vi.mock("./RegionManager", () => ({
  RegionManager: () => <div data-testid="region-manager" />,
}));

vi.mock("./AnnotationPanel", () => ({
  AnnotationPanel: () => <div data-testid="annotation-panel" />,
}));

vi.mock("./TranscriptPanel", () => ({
  TranscriptPanel: () => <div data-testid="transcript-panel" />,
}));

vi.mock("./SuggestionsPanel", () => ({
  SuggestionsPanel: () => <div data-testid="suggestions-panel" />,
}));

vi.mock("./ChatPanel", () => ({
  ChatPanel: () => <div data-testid="chat-panel" />,
}));

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function renderAnnotateMode() {
  return render(
    <MemoryRouter>
      <AnnotateMode />
    </MemoryRouter>,
  );
}

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("AnnotateMode", () => {
  beforeEach(() => {
    mockConfig = {
      project_name: "Test",
      language_code: "sdh",
      speakers: ["SPK_01", "SPK_02", "SPK_03"],
      audio_dir: "audio",
      annotations_dir: "annotations",
    };
    mockDirty = {};
    mockUIState = {
      activeSpeaker: null,
      activeConcept: null,
      annotatePanel: "annotation",
      onboardingComplete: true,
      setActiveSpeaker: vi.fn(),
      setActiveConcept: vi.fn(),
      setAnnotatePanel: vi.fn(),
      setOnboardingComplete: vi.fn(),
    };
    mockLoad.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders OnboardingFlow when onboardingComplete is false", () => {
    mockUIState.onboardingComplete = false;
    renderAnnotateMode();
    expect(screen.getByTestId("onboarding-flow")).toBeTruthy();
  });

  it("renders speaker list from config", () => {
    renderAnnotateMode();
    expect(screen.getByTestId("speaker-SPK_01")).toBeTruthy();
    expect(screen.getByTestId("speaker-SPK_02")).toBeTruthy();
    expect(screen.getByTestId("speaker-SPK_03")).toBeTruthy();
  });

  it("clicking a speaker sets activeSpeaker in uiStore", () => {
    renderAnnotateMode();
    fireEvent.click(screen.getByTestId("speaker-SPK_02"));
    expect(mockUIState.setActiveSpeaker).toHaveBeenCalledWith("SPK_02");
  });

  it("tab switching changes annotatePanel", () => {
    renderAnnotateMode();
    fireEvent.click(screen.getByTestId("tab-transcript"));
    expect(mockUIState.setAnnotatePanel).toHaveBeenCalledWith("transcript");
    fireEvent.click(screen.getByTestId("tab-suggestions"));
    expect(mockUIState.setAnnotatePanel).toHaveBeenCalledWith("suggestions");
    fireEvent.click(screen.getByTestId("tab-chat"));
    expect(mockUIState.setAnnotatePanel).toHaveBeenCalledWith("chat");
  });

  it("renders waveform container div", () => {
    renderAnnotateMode();
    expect(screen.getByTestId("waveform-container")).toBeTruthy();
  });
});
