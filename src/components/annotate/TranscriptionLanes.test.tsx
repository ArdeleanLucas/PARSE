// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { RefObject } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type WaveSurfer from "wavesurfer.js";
import legacyFail01 from "./__fixtures__/Fail01.legacy-tier-split.json";
import type { AnnotationRecord } from "../../api/types";


let mockRecord: AnnotationRecord | null = null;
let mockLanes: Record<string, { visible: boolean; color: string }> = {};
let mockSttBySpeaker: Record<string, unknown[]> = {};
let mockSttStatus: Record<string, "idle" | "loading" | "loaded" | "error"> = {};
let mockSelectedInterval: { speaker: string; tier: string; index: number } | null = null;

const mockEnsureStt = vi.fn();
const mockSetSelectedInterval = vi.fn();
const mockUpdateInterval = vi.fn();
const mockRemoveInterval = vi.fn();
const mockMergeIntervals = vi.fn();
const mockSplitInterval = vi.fn();
const mockAddInterval = vi.fn();
const mockEnsureSttTier = vi.fn();
const mockEnsureSttWordsTier = vi.fn();

vi.mock("../../stores/transcriptionLanesStore", () => ({
  LANE_LABELS: {
    ipa_phone: "Phone IPA",
    ipa: "IPA",
    stt: "STT",
    ortho: "ORTH",
    stt_words: "Words",
    boundaries: "BND",
  },
  useTranscriptionLanesStore: (selector: (state: unknown) => unknown) =>
    selector({
      lanes: mockLanes,
      sttBySpeaker: mockSttBySpeaker,
      sttStatus: mockSttStatus,
      ensureStt: mockEnsureStt,
      selectedInterval: mockSelectedInterval,
      setSelectedInterval: mockSetSelectedInterval,
    }),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (state: unknown) => unknown) =>
    selector({
      records: mockRecord ? { Fail01: mockRecord } : {},
      updateInterval: mockUpdateInterval,
      removeInterval: mockRemoveInterval,
      mergeIntervals: mockMergeIntervals,
      splitInterval: mockSplitInterval,
      addInterval: mockAddInterval,
      ensureSttTier: mockEnsureSttTier,
      ensureSttWordsTier: mockEnsureSttWordsTier,
    }),
}));

import { TranscriptionLanes } from "./TranscriptionLanes";

function makeRecord(): AnnotationRecord {
  return {
    speaker: "Fail01",
    tiers: {
      ipa: {
        name: "ipa",
        display_order: 1,
        intervals: [{ start: 1, end: 2, text: "aw" }],
      },
      ortho: {
        name: "ortho",
        display_order: 2,
        intervals: [{ start: 1, end: 2, text: "ئاو" }],
      },
      concept: {
        name: "concept",
        display_order: 3,
        intervals: [{ start: 1, end: 2, text: "water" }],
      },
      speaker: {
        name: "speaker",
        display_order: 4,
        intervals: [],
      },
    },
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    source_wav: "Fail01.wav",
  };
}

function createMockWaveSurfer({
  duration = 10,
  minPxPerSec = 120,
  viewportScrollLeft = 0,
}: { duration?: number; minPxPerSec?: number; viewportScrollLeft?: number } = {}): WaveSurfer {
  const viewport = document.createElement("div");
  Object.defineProperty(viewport, "clientWidth", { value: 640, configurable: true });
  viewport.scrollLeft = viewportScrollLeft;
  const wrapper = document.createElement("div");
  Object.defineProperty(wrapper, "clientWidth", { value: Math.max(640, duration * minPxPerSec), configurable: true });
  viewport.appendChild(wrapper);

  const listeners = new Map<string, Set<(...args: unknown[]) => void>>();
  return {
    options: { minPxPerSec },
    getDuration: () => duration,
    getWrapper: () => wrapper,
    on: (event: string, handler: (...args: unknown[]) => void) => {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)?.add(handler);
    },
    un: (event: string, handler: (...args: unknown[]) => void) => {
      listeners.get(event)?.delete(handler);
    },
    getCurrentTime: () => 0,
  } as unknown as WaveSurfer;
}

describe("TranscriptionLanes", () => {
  beforeEach(() => {
    mockRecord = makeRecord();
    mockLanes = {
      ipa_phone: { visible: false, color: "#a855f7" },
      ipa: { visible: true, color: "#0f172a" },
      stt: { visible: false, color: "#1d4ed8" },
      ortho: { visible: true, color: "#059669" },
      stt_words: { visible: false, color: "#7c3aed" },
      boundaries: { visible: false, color: "#dc2626" },
    };
    mockSttBySpeaker = {};
    mockSttStatus = { Fail01: "idle" };
    mockSelectedInterval = null;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("renders after waveform metrics initialize without triggering a hook-order crash", async () => {
    const wsRef = { current: createMockWaveSurfer() } as RefObject<WaveSurfer | null>;

    render(
      <TranscriptionLanes
        speaker="Fail01"
        wsRef={wsRef}
        audioReady={true}
        onSeek={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByTitle("IPA lane")).toBeTruthy());
    expect(screen.getByTitle("ORTH lane")).toBeTruthy();
  });

  it("renders the trimmed Fail01 legacy fixture without requiring a migrated stt_words tier", async () => {
    mockLanes.stt_words.visible = true;
    mockLanes.boundaries.visible = true;
    mockRecord = structuredClone(legacyFail01) as AnnotationRecord;
    mockSttBySpeaker = {
      Fail01: [
        {
          start: 0,
          end: 3.56,
          text: "försچ ڕی یان",
          words: [
            { start: 0.0, end: 0.28, word: "försچ" },
            { start: 0.28, end: 1.12, word: "یان" },
            { start: 1.12, end: 3.56, word: "ڕی" },
          ],
        },
      ],
    };
    mockSttStatus = { Fail01: "loaded" };

    const wsRef = { current: createMockWaveSurfer() } as RefObject<WaveSurfer | null>;
    render(
      <TranscriptionLanes
        speaker="Fail01"
        wsRef={wsRef}
        audioReady={true}
        onSeek={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByTitle("Words lane")).toBeTruthy());
    expect(screen.getByTitle("BND lane")).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Words 0.00s' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'BND 0.00s' })).toBeTruthy();
    expect(mockEnsureSttWordsTier).not.toHaveBeenCalled();
    expect((mockRecord?.tiers as Record<string, unknown>).stt_words).toBeUndefined();
  });

  it("virtualizes BND markers from the WaveSurfer viewport scroll position", async () => {
    mockLanes.boundaries.visible = true;
    mockLanes.ipa.visible = false;
    mockLanes.ortho.visible = false;
    mockRecord = makeRecord();
    mockRecord.tiers.ortho_words = {
      name: "ortho_words",
      display_order: 4,
      intervals: [
        ...Array.from({ length: 220 }, (_, i) => ({
          start: i * 2,
          end: i * 2 + 0.2,
          text: `early-${i}`,
        })),
        { start: 6207.686, end: 6207.736, text: "bnd-at-region", manuallyAdjusted: true },
      ],
    };

    const wsRef = {
      current: createMockWaveSurfer({
        duration: 9118.263,
        minPxPerSec: 400,
        viewportScrollLeft: 6207.686 * 400 - 200,
      }),
    } as RefObject<WaveSurfer | null>;
    render(
      <TranscriptionLanes
        speaker="Fail01"
        wsRef={wsRef}
        audioReady={true}
        onSeek={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByTitle("BND lane")).toBeTruthy());
    expect(screen.getByRole("button", { name: "BND 6207.69s" })).toBeTruthy();
  });
});
