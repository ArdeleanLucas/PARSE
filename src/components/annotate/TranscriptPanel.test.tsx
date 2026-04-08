// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { AnnotationRecord, AnnotationInterval } from "../../api/types";

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

let mockActiveSpeaker: string | null = null;
let mockCurrentTime = 0;
let mockRecords: Record<string, AnnotationRecord> = {};

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (
    selector: (s: { activeSpeaker: string | null }) => unknown,
  ) => selector({ activeSpeaker: mockActiveSpeaker }),
}));

vi.mock("../../stores/playbackStore", () => ({
  usePlaybackStore: (
    selector: (s: { currentTime: number }) => unknown,
  ) => selector({ currentTime: mockCurrentTime }),
}));

vi.mock("../../stores/annotationStore", () => ({
  useAnnotationStore: (selector: (s: { records: Record<string, AnnotationRecord> }) => unknown) =>
    selector({ records: mockRecords }),
}));

import { TranscriptPanel } from "./TranscriptPanel";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function makeRecord(speaker: string, ipaIntervals: AnnotationInterval[] = []): AnnotationRecord {
  return {
    speaker,
    tiers: {
      ipa: { name: "ipa", display_order: 1, intervals: ipaIntervals },
      ortho: { name: "ortho", display_order: 2, intervals: [] },
      concept: { name: "concept", display_order: 3, intervals: [] },
      speaker: { name: "speaker", display_order: 4, intervals: [] },
    },
    created_at: "2026-01-01T00:00:00.000Z",
    modified_at: "2026-01-01T00:00:00.000Z",
    source_wav: "",
  };
}

const MOCK_INTERVALS: AnnotationInterval[] = [
  { start: 1.2, end: 2.0, text: "hello world" },
  { start: 5.8, end: 7.0, text: "foo bar" },
  { start: 10.0, end: 12.5, text: "hello again" },
];

/* ------------------------------------------------------------------ */
/*  Setup / teardown                                                   */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  mockActiveSpeaker = null;
  mockCurrentTime = 0;
  mockRecords = {};
});

afterEach(cleanup);

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("TranscriptPanel", () => {
  it('renders "No transcript segments" when record is null', () => {
    mockActiveSpeaker = null;
    const onSeek = vi.fn();
    render(<TranscriptPanel onSeek={onSeek} />);
    expect(screen.getByText("No transcript segments")).toBeTruthy();
  });

  it("renders all segment rows when record has intervals", () => {
    mockActiveSpeaker = "spk1";
    mockRecords = { spk1: makeRecord("spk1", MOCK_INTERVALS) };
    const onSeek = vi.fn();
    render(<TranscriptPanel onSeek={onSeek} />);

    const rows = screen.getAllByTestId("transcript-row");
    expect(rows).toHaveLength(3);
    expect(screen.getByText("hello world")).toBeTruthy();
    expect(screen.getByText("foo bar")).toBeTruthy();
    expect(screen.getByText("hello again")).toBeTruthy();
  });

  it("search filters rows by text match", () => {
    mockActiveSpeaker = "spk1";
    mockRecords = { spk1: makeRecord("spk1", MOCK_INTERVALS) };
    const onSeek = vi.fn();
    render(<TranscriptPanel onSeek={onSeek} />);

    const input = screen.getByLabelText("Search segments");
    fireEvent.change(input, { target: { value: "hello" } });

    const rows = screen.getAllByTestId("transcript-row");
    expect(rows).toHaveLength(2);
    // "foo bar" should not be present
    expect(screen.queryByText("foo bar")).toBeNull();
  });

  it("clicking a row calls onSeek with segment.start", () => {
    mockActiveSpeaker = "spk1";
    mockRecords = { spk1: makeRecord("spk1", MOCK_INTERVALS) };
    const onSeek = vi.fn();
    render(<TranscriptPanel onSeek={onSeek} />);

    const rows = screen.getAllByTestId("transcript-row");
    fireEvent.click(rows[1]); // "foo bar" at start=5.8
    expect(onSeek).toHaveBeenCalledWith(5.8);
  });

  it("active row is highlighted when currentTime matches a segment", () => {
    mockActiveSpeaker = "spk1";
    mockCurrentTime = 6.0; // between 5.8 and 10.0, so segment index 1 is active
    mockRecords = { spk1: makeRecord("spk1", MOCK_INTERVALS) };
    const onSeek = vi.fn();
    render(<TranscriptPanel onSeek={onSeek} />);

    const rows = screen.getAllByTestId("transcript-row");
    // Row at index 1 ("foo bar") should have active styles (jsdom normalizes hex to rgb)
    const activeBg = rows[1].style.backgroundColor;
    expect(activeBg === "#f0f7ff" || activeBg === "rgb(240, 247, 255)").toBe(true);
    const activeBorder = rows[1].style.borderLeft;
    expect(activeBorder).toContain("3px solid");
    expect(activeBorder === "3px solid #3b82f6" || activeBorder === "3px solid rgb(59, 130, 246)").toBe(true);
    // Other rows should not have active background
    expect(rows[0].style.backgroundColor).toBe("transparent");
    expect(rows[2].style.backgroundColor).toBe("transparent");
  });
});
