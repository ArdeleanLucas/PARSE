// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TranscriptionRunGrid } from "../TranscriptionRunGrid";
import type {
  PipelineStepId,
  RunScope,
  SpeakerLoadEntry,
} from "../transcriptionRunShared";

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

function GridHarness({
  speakers,
  gridStepColumns,
  stateBySpeaker,
  initialSelectedSpeakers,
  initialScopeByStep,
}: {
  speakers: string[];
  gridStepColumns: PipelineStepId[];
  stateBySpeaker: Record<string, SpeakerLoadEntry>;
  initialSelectedSpeakers: string[];
  initialScopeByStep?: Partial<Record<PipelineStepId, RunScope>>;
}) {
  const [selectedSpeakers, setSelectedSpeakers] = useState<Set<string>>(
    () => new Set(initialSelectedSpeakers),
  );
  const [scopeByStep, setScopeByStep] = useState<Record<PipelineStepId, RunScope>>(() => ({
    normalize: initialScopeByStep?.normalize ?? "gaps",
    stt: initialScopeByStep?.stt ?? "gaps",
    ortho: initialScopeByStep?.ortho ?? "gaps",
    ipa: initialScopeByStep?.ipa ?? "gaps",
  }));

  return (
    <TranscriptionRunGrid
      speakers={speakers}
      gridStepColumns={gridStepColumns}
      selectedSpeakers={selectedSpeakers}
      stateBySpeaker={stateBySpeaker}
      scopeByStep={scopeByStep}
      onToggleSpeaker={(speaker) => {
        setSelectedSpeakers((prev) => {
          const next = new Set(prev);
          if (next.has(speaker)) next.delete(speaker);
          else next.add(speaker);
          return next;
        });
      }}
      onSetAllSpeakers={setSelectedSpeakers}
      onSetStepScope={(step, scope) => {
        setScopeByStep((prev) => ({ ...prev, [step]: scope }));
      }}
    />
  );
}

describe("TranscriptionRunGrid", () => {
  afterEach(() => cleanup());

  it("renders grid rows and cell kinds for ok, skip, blocked, and keep-existing states", () => {
    const stateBySpeaker: Record<string, SpeakerLoadEntry> = {
      Alpha: { status: "ready", state: makeState({ speaker: "Alpha" }), error: null },
      Beta: {
        status: "ready",
        state: makeState({
          speaker: "Beta",
          sttDone: true,
          sttSegments: 12,
          orthoDone: true,
          orthoIntervals: 42,
          orthoCanRun: true,
        }),
        error: null,
      },
      Broken: { status: "error", state: null, error: "network" },
    };

    render(
      <GridHarness
        speakers={["Alpha", "Beta", "Broken"]}
        gridStepColumns={["stt", "ortho"]}
        stateBySpeaker={stateBySpeaker}
        initialSelectedSpeakers={["Beta"]}
      />,
    );

    expect(screen.getByTestId("transcription-run-row-Alpha")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-row-Beta")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-row-Broken")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-cell-Alpha-stt").getAttribute("data-cell-kind")).toBe("ok");
    expect(screen.getByTestId("transcription-run-cell-Beta-stt").getAttribute("data-cell-kind")).toBe("keep");
    expect(screen.getByTestId("transcription-run-cell-Beta-ortho").getAttribute("data-cell-kind")).toBe("keep");
    expect((screen.getByTestId("transcription-run-speaker-Broken") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText(/failed to load state/i)).toBeTruthy();
  });

  it("speaker toolbar supports select all, visible-runnable, and none", () => {
    const stateBySpeaker: Record<string, SpeakerLoadEntry> = {
      Alpha: { status: "ready", state: makeState({ speaker: "Alpha" }), error: null },
      Beta: {
        status: "ready",
        state: makeState({
          speaker: "Beta",
          sttCanRun: false,
          sttReason: "No audio",
        }),
        error: null,
      },
      Broken: { status: "error", state: null, error: "network" },
    };

    render(
      <GridHarness
        speakers={["Alpha", "Beta", "Broken"]}
        gridStepColumns={["stt"]}
        stateBySpeaker={stateBySpeaker}
        initialSelectedSpeakers={[]}
      />,
    );

    act(() => {
      fireEvent.click(screen.getByTestId("transcription-run-select-all"));
    });
    expect((screen.getByTestId("transcription-run-speaker-Alpha") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId("transcription-run-speaker-Beta") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId("transcription-run-speaker-Broken") as HTMLInputElement).checked).toBe(false);

    act(() => {
      fireEvent.click(screen.getByTestId("transcription-run-select-none"));
    });
    expect((screen.getByTestId("transcription-run-speaker-Alpha") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByTestId("transcription-run-speaker-Beta") as HTMLInputElement).checked).toBe(false);

    act(() => {
      fireEvent.click(screen.getByTestId("transcription-run-select-runnable"));
    });
    expect((screen.getByTestId("transcription-run-speaker-Alpha") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId("transcription-run-speaker-Beta") as HTMLInputElement).checked).toBe(false);
  });

  it("scope toggles update the rendered cell kind from keep to overwrite", () => {
    const stateBySpeaker: Record<string, SpeakerLoadEntry> = {
      Beta: {
        status: "ready",
        state: makeState({
          speaker: "Beta",
          orthoDone: true,
          orthoIntervals: 42,
        }),
        error: null,
      },
    };

    render(
      <GridHarness
        speakers={["Beta"]}
        gridStepColumns={["ortho"]}
        stateBySpeaker={stateBySpeaker}
        initialSelectedSpeakers={["Beta"]}
      />,
    );

    expect(screen.getByTestId("transcription-run-cell-Beta-ortho").getAttribute("data-cell-kind")).toBe("keep");
    act(() => {
      fireEvent.click(screen.getByTestId("transcription-run-scope-ortho-overwrite"));
    });
    expect(screen.getByTestId("transcription-run-cell-Beta-ortho").getAttribute("data-cell-kind")).toBe("overwrite");
    expect(screen.getByTestId("transcription-run-scope-ortho").getAttribute("data-step-scope")).toBe("overwrite");
  });
});
