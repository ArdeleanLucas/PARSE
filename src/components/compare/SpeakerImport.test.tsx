// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/* ------------------------------------------------------------------ */
/*  Mock client helpers                                                */
/* ------------------------------------------------------------------ */

const mockOnboardSpeaker = vi.fn();
const mockPollOnboardSpeaker = vi.fn();

vi.mock("../../api/client", () => ({
  onboardSpeaker: (...args: unknown[]) => mockOnboardSpeaker(...args),
  pollOnboardSpeaker: (...args: unknown[]) => mockPollOnboardSpeaker(...args),
}));

import { SpeakerImport } from "./SpeakerImport";

function makeFile(name: string, type: string): File {
  return new File(["dummy"], name, { type });
}

function fillFormAndStart() {
  fireEvent.change(screen.getByTestId("speaker-id-input"), {
    target: { value: "spk1" },
  });

  const audioInput = screen.getByTestId("audio-file-input");
  const file = makeFile("test.wav", "audio/wav");
  Object.defineProperty(audioInput, "files", { value: [file], configurable: true });
  fireEvent.change(audioInput);

  fireEvent.click(screen.getByTestId("start-import-btn"));
}

beforeEach(() => {
  mockOnboardSpeaker.mockReset();
  mockPollOnboardSpeaker.mockReset();
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("SpeakerImport", () => {
  it("Start Import disabled when no speakerId", () => {
    render(<SpeakerImport />);
    const btn = screen.getByTestId("start-import-btn");
    expect(btn).toBeInstanceOf(HTMLButtonElement);
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("Start Import disabled when no audioFile", () => {
    render(<SpeakerImport />);
    const input = screen.getByTestId("speaker-id-input");
    fireEvent.change(input, { target: { value: "spk1" } });
    const btn = screen.getByTestId("start-import-btn");
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("Successful import: onboardSpeaker called, onImportComplete called", async () => {
    const onComplete = vi.fn();

    mockOnboardSpeaker.mockResolvedValueOnce({ job_id: "job-123" });

    mockPollOnboardSpeaker.mockResolvedValueOnce({
      status: "done",
      progress: 100,
      segments: [],
    });

    render(<SpeakerImport onImportComplete={onComplete} />);
    fillFormAndStart();

    // Let upload resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(mockOnboardSpeaker).toHaveBeenCalledWith(
      "spk1",
      expect.any(File),
      null,
    );

    // Advance past the 2s poll delay
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(mockPollOnboardSpeaker).toHaveBeenCalledWith("job-123");
    expect(onComplete).toHaveBeenCalledWith("spk1");
  });

  it("Upload error shows error message", async () => {
    mockOnboardSpeaker.mockRejectedValueOnce(
      new Error("Onboarding endpoint not available")
    );

    render(<SpeakerImport />);
    fillFormAndStart();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(screen.getByTestId("import-error")).toBeTruthy();
    expect(screen.getByText("Onboarding endpoint not available")).toBeTruthy();
  });

  it("Poll error status shows error message", async () => {
    mockOnboardSpeaker.mockResolvedValueOnce({ job_id: "job-456" });

    mockPollOnboardSpeaker.mockResolvedValueOnce({
      status: "error",
      progress: 50,
      segments: [],
    });

    render(<SpeakerImport />);
    fillFormAndStart();

    // Let upload resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    // Advance past poll delay
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(screen.getByTestId("import-error")).toBeTruthy();
    expect(screen.getByText("Processing failed on server")).toBeTruthy();
  });
});
