// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

let mockActiveSpeaker: string | null = null;
let mockActiveConcept: string | null = null;
let mockSelectedRegion: { start: number; end: number } | null = null;

vi.mock("../../stores/uiStore", () => ({
  useUIStore: (selector: (s: { activeSpeaker: string | null; activeConcept: string | null }) => unknown) =>
    selector({ activeSpeaker: mockActiveSpeaker, activeConcept: mockActiveConcept }),
}));

vi.mock("../../stores/playbackStore", () => ({
  usePlaybackStore: (selector: (s: { selectedRegion: { start: number; end: number } | null }) => unknown) =>
    selector({ selectedRegion: mockSelectedRegion }),
}));

import { RegionManager } from "./RegionManager";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function seedDecisions(conceptId: string, speaker: string, start: number, end: number) {
  const decisions: Record<string, Record<string, unknown>> = {
    [conceptId]: {
      [speaker]: {
        source_wav: null,
        start_sec: start,
        end_sec: end,
        assigned: true,
        replaces_segment: true,
      },
    },
  };
  localStorage.setItem("parse-decisions", JSON.stringify(decisions));
}

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe("RegionManager", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockActiveSpeaker = null;
    mockActiveConcept = null;
    mockSelectedRegion = null;
    localStorage.clear();
  });

  it('renders "No region selected" when selectedRegion is null', () => {
    render(<RegionManager onSeek={vi.fn()} />);
    expect(screen.getByText("No region selected")).toBeTruthy();
  });

  it("shows current region start/end when selectedRegion is set", () => {
    mockSelectedRegion = { start: 1.234, end: 5.678 };
    render(<RegionManager onSeek={vi.fn()} />);
    expect(screen.getByText(/1\.234 s/)).toBeTruthy();
    expect(screen.getByText(/5\.678 s/)).toBeTruthy();
  });

  it('"Assign to concept" button is disabled when selectedRegion is null', () => {
    render(<RegionManager onSeek={vi.fn()} />);
    const btn = screen.getByRole("button", { name: "Assign to concept" });
    expect(btn).toBeInstanceOf(HTMLButtonElement);
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('"Assign to concept" calls onAssigned with correct speaker/concept/start/end', () => {
    mockActiveSpeaker = "Fail01";
    mockActiveConcept = "42";
    mockSelectedRegion = { start: 1.5, end: 3.5 };

    const onAssigned = vi.fn();
    render(<RegionManager onSeek={vi.fn()} onAssigned={onAssigned} />);

    const btn = screen.getByRole("button", { name: "Assign to concept" });
    fireEvent.click(btn);

    expect(onAssigned).toHaveBeenCalledWith("Fail01", "42", 1.5, 3.5);
  });

  it('stores prior regions in the oracle parse-decisions key', () => {
    mockActiveSpeaker = "Fail01";
    mockActiveConcept = "42";
    mockSelectedRegion = { start: 1.5, end: 3.5 };

    render(<RegionManager onSeek={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Assign to concept" }));

    expect(JSON.parse(localStorage.getItem("parse-decisions") ?? "{}")).toEqual({
      "42": {
        Fail01: {
          source_wav: null,
          start_sec: 1.5,
          end_sec: 3.5,
          assigned: true,
          replaces_segment: true,
        },
      },
    });
  });

  it('"Load prior region" reads from the oracle parse-decisions key', () => {
    mockActiveSpeaker = "Fail01";
    mockActiveConcept = "42";
    seedDecisions("42", "Fail01", 1.2, 1.7);

    const onSeek = vi.fn();
    render(<RegionManager onSeek={onSeek} />);

    const btn = screen.getByRole("button", { name: "Load prior region" });
    fireEvent.click(btn);

    expect(onSeek).toHaveBeenCalledWith(1.2, true, 0.5);
  });

  it('"Load prior region" calls onSeek with prior decision coordinates', () => {
    mockActiveSpeaker = "Fail01";
    mockActiveConcept = "42";
    seedDecisions("42", "Fail01", 0.5, 3.0);

    const onSeek = vi.fn();
    render(<RegionManager onSeek={onSeek} />);

    const btn = screen.getByRole("button", { name: "Load prior region" });
    fireEvent.click(btn);

    expect(onSeek).toHaveBeenCalledWith(0.5, true, 2.5);
  });
});
