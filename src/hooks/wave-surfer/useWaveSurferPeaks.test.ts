// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { loadWaveSurferAudio } from "./useWaveSurferPeaks";

describe("loadWaveSurferAudio", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches peak JSON with no-store so rebuilt workspace peaks cannot stay visually stale", async () => {
    const abortCtrl = new AbortController();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ channels: 1, data: [0, 1, -1, 0.5] }),
    } as Response);
    const ws = { load: vi.fn() };

    await loadWaveSurferAudio(
      ws as never,
      {
        containerRef: { current: document.createElement("div") },
        audioUrl: "/audio/working/Qasr01/Qasrashirin_M_1973.wav",
        peaksUrl: "/peaks/Qasr01.json",
      },
      abortCtrl,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/peaks/Qasr01.json",
      expect.objectContaining({ signal: abortCtrl.signal, cache: "no-store" }),
    );
    expect(ws.load).toHaveBeenCalledWith(
      "/audio/working/Qasr01/Qasrashirin_M_1973.wav",
      [[0, 1, -1, 0.5]],
      undefined,
    );
  });
});
