import { describe, expect, it } from "vitest";

import { formatPlaybackTime, formatPlayhead } from "./shared";

describe("annotate view time formatting", () => {
  it("formats waveform playhead time with two decimals while preserving padding", () => {
    expect(formatPlayhead(0)).toBe("0:00.00");
    expect(formatPlayhead(5.125)).toBe("0:05.13");
    expect(formatPlayhead(65.1)).toBe("1:05.10");
    expect(formatPlayhead(-1)).toBe("0:00.00");
  });

  it("keeps playback timestamps on their existing two-decimal formatter", () => {
    expect(formatPlaybackTime(5.125)).toBe("00:05.12");
  });
});
