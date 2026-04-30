import { describe, expect, it } from "vitest";
import { computeCell, type SpeakerLoadEntry } from "../transcriptionRunShared";

function makeState(overrides: Partial<{
  speaker: string;
  normalizeDone: boolean;
  normalizeCanRun: boolean;
  normalizeReason: string | null;
  sttDone: boolean;
  sttCanRun: boolean;
  sttReason: string | null;
  sttSegments: number;
  orthoDone: boolean;
  orthoCanRun: boolean;
  orthoReason: string | null;
  orthoIntervals: number;
  ipaDone: boolean;
  ipaCanRun: boolean;
  ipaReason: string | null;
  ipaIntervals: number;
}> = {}) {
  return {
    speaker: overrides.speaker ?? "Sp",
    normalize: {
      done: overrides.normalizeDone ?? false,
      can_run: overrides.normalizeCanRun ?? true,
      reason: overrides.normalizeReason ?? null,
      path: overrides.normalizeDone ? "audio/working/Sp/Sp.wav" : null,
    },
    stt: {
      done: overrides.sttDone ?? false,
      can_run: overrides.sttCanRun ?? true,
      reason: overrides.sttReason ?? null,
      segments: overrides.sttSegments ?? 0,
    },
    ortho: {
      done: overrides.orthoDone ?? false,
      can_run: overrides.orthoCanRun ?? true,
      reason: overrides.orthoReason ?? null,
      intervals: overrides.orthoIntervals ?? 0,
    },
    ipa: {
      done: overrides.ipaDone ?? false,
      can_run: overrides.ipaCanRun ?? true,
      reason: overrides.ipaReason ?? null,
      intervals: overrides.ipaIntervals ?? 0,
    },
  };
}

function makeEntry(overrides: Parameters<typeof makeState>[0]): SpeakerLoadEntry {
  return { status: "ready", state: makeState(overrides), error: null };
}

describe("computeCell", () => {
  it("treats stale IPA can_run=false as runnable in concept-window modes when concept-tier presence is observable", () => {
    expect(
      computeCell(
        "ipa",
        makeEntry({ ipaCanRun: false, ipaReason: "No ORTH", orthoIntervals: 523, orthoCanRun: true }),
        true,
        "gaps",
        "concept-windows",
      ).kind,
    ).toBe("ok");

    expect(
      computeCell(
        "ipa",
        makeEntry({ ipaCanRun: false, ipaReason: "No ORTH", orthoIntervals: 0, orthoCanRun: true }),
        true,
        "gaps",
        "edited-only",
      ).kind,
    ).toBe("ok");
  });

  it("keeps IPA blocked when concept-tier presence is absent or the run mode is full", () => {
    expect(
      computeCell(
        "ipa",
        makeEntry({ ipaCanRun: false, ipaReason: "No ORTH", orthoIntervals: 0, orthoCanRun: false }),
        true,
        "gaps",
        "concept-windows",
      ).kind,
    ).toBe("blocked");

    expect(
      computeCell(
        "ipa",
        makeEntry({ ipaCanRun: false, ipaReason: "No ORTH", orthoIntervals: 523, orthoCanRun: true }),
        true,
        "gaps",
        "full",
      ).kind,
    ).toBe("blocked");
  });

  it("does not override blocked ORTH cells in concept-window modes", () => {
    expect(
      computeCell(
        "ortho",
        makeEntry({ orthoCanRun: false, orthoReason: "No concept tier", orthoIntervals: 523 }),
        true,
        "gaps",
        "concept-windows",
      ).kind,
    ).toBe("blocked");
  });
});
