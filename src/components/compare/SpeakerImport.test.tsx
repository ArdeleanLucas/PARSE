// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/* ------------------------------------------------------------------ */
/*  Mock pollSTT from client                                           */
/* ------------------------------------------------------------------ */

const mockPollSTT = vi.fn();

vi.mock("../../api/client", () => ({
  pollSTT: (...args: unknown[]) => mockPollSTT(...args),
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
  mockPollSTT.mockReset();
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

  it("Successful import: fetch called with FormData, onImportComplete called", async () => {
    const onComplete = vi.fn();

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ job_id: "job-123" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    mockPollSTT.mockResolvedValueOnce({
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

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/onboard/speaker",
      expect.objectContaining({ method: "POST" })
    );

    // Advance past the 2s poll delay
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(mockPollSTT).toHaveBeenCalledWith("job-123");
    expect(onComplete).toHaveBeenCalledWith("spk1");
  });

  it("HTTP error shows error message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("Not Found", { status: 404 })
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
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ job_id: "job-456" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    mockPollSTT.mockResolvedValueOnce({
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
