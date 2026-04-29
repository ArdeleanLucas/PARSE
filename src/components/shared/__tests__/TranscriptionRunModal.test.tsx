// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  TranscriptionRunModal,
  type TranscriptionRunConfirm,
} from "../TranscriptionRunModal";

vi.mock("../../../api/client", () => ({
  getAnnotation: vi.fn(),
  getPipelineState: vi.fn(),
}));

import { getAnnotation, getPipelineState } from "../../../api/client";

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

describe("TranscriptionRunModal", () => {
  beforeEach(() => {
    vi.mocked(getPipelineState).mockReset();
    vi.mocked(getAnnotation).mockReset();
    vi.mocked(getAnnotation).mockResolvedValue({
      speaker: "Sp",
      tiers: { concept: { name: "concept", display_order: 0, intervals: [] } },
    });
  });
  afterEach(() => {
    cleanup();
  });

  it("pre-checks defaultSelectedSpeaker (Test A)", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha", "Beta", "Gamma"]}
        defaultSelectedSpeaker="Beta"
        title="Run Full Pipeline"
      />,
    );

    const alpha = (await screen.findByTestId(
      "transcription-run-speaker-Alpha",
    )) as HTMLInputElement;
    const beta = screen.getByTestId(
      "transcription-run-speaker-Beta",
    ) as HTMLInputElement;
    const gamma = screen.getByTestId(
      "transcription-run-speaker-Gamma",
    ) as HTMLInputElement;

    expect(alpha.checked).toBe(false);
    expect(beta.checked).toBe(true);
    expect(gamma.checked).toBe(false);
  });

  it("hides step checkboxes and renders only one step column when fixedSteps is set (Test B)", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha"]}
        defaultSelectedSpeaker="Alpha"
        fixedSteps={["stt"]}
        title="Run STT"
      />,
    );

    await screen.findByTestId("transcription-run-speaker-Alpha");

    expect(screen.queryByTestId("transcription-run-step-checkboxes")).toBeNull();
    expect(screen.getByTestId("transcription-run-col-stt")).toBeTruthy();
    expect(screen.queryByTestId("transcription-run-col-normalize")).toBeNull();
    expect(screen.queryByTestId("transcription-run-col-ortho")).toBeNull();
    expect(screen.queryByTestId("transcription-run-col-ipa")).toBeNull();
  });

  it("badges reflect preflight state: ok, will-skip, blocked (Test C)", async () => {
    // Alpha: all can_run, nothing done → ok cells
    // Beta: stt done=true (→ skip when not selected), ortho blocked
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) => {
      if (speaker === "Alpha") return makeState({ speaker: "Alpha" });
      if (speaker === "Beta")
        return makeState({
          speaker: "Beta",
          sttDone: true,
          sttSegments: 12,
          orthoCanRun: false,
          orthoReason: "No STT segments",
        });
      return makeState({ speaker });
    });

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha", "Beta"]}
        defaultSelectedSpeaker={null}
        title="Run Full Pipeline"
      />,
    );

    // Wait for both rows to load.
    await waitFor(() => {
      expect(
        screen
          .getByTestId("transcription-run-cell-Alpha-stt")
          .getAttribute("data-cell-kind"),
      ).not.toBe("loading");
      expect(
        screen
          .getByTestId("transcription-run-cell-Beta-stt")
          .getAttribute("data-cell-kind"),
      ).not.toBe("loading");
    });

    // Alpha/stt → ok (not done, can_run, alpha not selected-but-state shows ok)
    const alphaStt = screen.getByTestId("transcription-run-cell-Alpha-stt");
    expect(alphaStt.getAttribute("data-cell-kind")).toBe("ok");

    // Beta/stt → skip (done + alpha not selected)
    const betaStt = screen.getByTestId("transcription-run-cell-Beta-stt");
    expect(betaStt.getAttribute("data-cell-kind")).toBe("skip");

    // Beta/ortho → blocked
    const betaOrtho = screen.getByTestId("transcription-run-cell-Beta-ortho");
    expect(betaOrtho.getAttribute("data-cell-kind")).toBe("blocked");
  });

  it("onConfirm defaults to keep-existing scope (no implicit overwrite) (Test D)", async () => {
    // Beta has ortho done=true. Re-ticking ortho surfaces the scope bar; by
    // default scope is "gaps" so confirming does NOT set overwrites.ortho —
    // this protects finalized work from being clobbered on accident.
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) => {
      if (speaker === "Beta")
        return makeState({
          speaker: "Beta",
          orthoDone: true,
          orthoIntervals: 42,
        });
      return makeState({ speaker });
    });

    const onConfirm = vi.fn<[TranscriptionRunConfirm], void>();
    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={onConfirm}
        speakers={["Alpha", "Beta"]}
        defaultSelectedSpeaker="Beta"
        title="Run Full Pipeline"
      />,
    );

    await waitFor(() => {
      const orthoStep = screen.getByTestId(
        "transcription-run-step-ortho",
      ) as HTMLInputElement;
      expect(orthoStep.checked).toBe(false);
    });

    const orthoStep = screen.getByTestId(
      "transcription-run-step-ortho",
    ) as HTMLInputElement;
    act(() => {
      fireEvent.click(orthoStep);
    });

    // Collision detected → cell is `keep` (not `overwrite`) and scope bar
    // shows the Keep/Overwrite toggle for ortho defaulted to Keep.
    await waitFor(() => {
      expect(
        screen
          .getByTestId("transcription-run-cell-Beta-ortho")
          .getAttribute("data-cell-kind"),
      ).toBe("keep");
    });
    const scopeBar = screen.getByTestId("transcription-run-scope-bar");
    expect(scopeBar).toBeTruthy();
    expect(
      screen
        .getByTestId("transcription-run-scope-ortho")
        .getAttribute("data-step-scope"),
    ).toBe("gaps");

    const confirmBtn = screen.getByTestId(
      "transcription-run-confirm",
    ) as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(false);
    act(() => {
      fireEvent.click(confirmBtn);
    });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const arg = onConfirm.mock.calls[0][0];
    expect(arg.speakers).toEqual(["Beta"]);
    expect(arg.steps).toEqual(["normalize", "stt", "ortho", "ipa"]);
    // Default scope is "gaps" for ortho → no overwrite flag is sent.
    expect(arg.overwrites.ortho).toBeUndefined();
    expect(arg.overwrites.normalize).toBeUndefined();
    expect(arg.overwrites.stt).toBeUndefined();
    expect(arg.overwrites.ipa).toBeUndefined();
  });

  it("flipping a collision step to Overwrite sends overwrites[step]=true (Test G)", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) => {
      if (speaker === "Beta")
        return makeState({
          speaker: "Beta",
          orthoDone: true,
          orthoIntervals: 42,
        });
      return makeState({ speaker });
    });

    const onConfirm = vi.fn<[TranscriptionRunConfirm], void>();
    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={onConfirm}
        speakers={["Beta"]}
        defaultSelectedSpeaker="Beta"
        fixedSteps={["ortho"]}
        title="Generate ORTH"
      />,
    );

    // Wait for Beta's state to resolve, and for the collision bar to render
    // (Beta is the default speaker, ortho is the fixed step, and Beta has
    // ortho.done=true).
    await waitFor(() => {
      expect(screen.getByTestId("transcription-run-scope-bar")).toBeTruthy();
    });

    // Default scope is `gaps` → cell is `keep`.
    expect(
      screen
        .getByTestId("transcription-run-cell-Beta-ortho")
        .getAttribute("data-cell-kind"),
    ).toBe("keep");

    // Flip ortho to Overwrite.
    const overwriteBtn = screen.getByTestId(
      "transcription-run-scope-ortho-overwrite",
    );
    act(() => {
      fireEvent.click(overwriteBtn);
    });

    // Cell flips to `overwrite` and scope attr is updated.
    await waitFor(() => {
      expect(
        screen
          .getByTestId("transcription-run-cell-Beta-ortho")
          .getAttribute("data-cell-kind"),
      ).toBe("overwrite");
    });
    expect(
      screen
        .getByTestId("transcription-run-scope-ortho")
        .getAttribute("data-step-scope"),
    ).toBe("overwrite");

    act(() => {
      fireEvent.click(screen.getByTestId("transcription-run-confirm"));
    });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const arg = onConfirm.mock.calls[0][0];
    expect(arg.speakers).toEqual(["Beta"]);
    expect(arg.steps).toEqual(["ortho"]);
    expect(arg.overwrites.ortho).toBe(true);
  });

  it("Run button disabled when nothing selected (Test E)", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha"]}
        defaultSelectedSpeaker={null}
        title="Run Full Pipeline"
      />,
    );

    const confirm = (await screen.findByTestId(
      "transcription-run-confirm",
    )) as HTMLButtonElement;
    // No default speaker → nothing selected → disabled.
    expect(confirm.disabled).toBe(true);
  });

  it("renders run-mode radios and defaults to full audio", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha"]}
        defaultSelectedSpeaker="Alpha"
        title="Run Full Pipeline"
      />,
    );

    await screen.findByTestId("transcription-run-speaker-Alpha");
    expect(screen.getByRole("radio", { name: /full audio/i })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /all concept windows/i })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /edited concepts only/i })).toBeTruthy();
    expect((screen.getByRole("radio", { name: /full audio/i }) as HTMLInputElement).checked).toBe(true);
  });

  it("hides Normalize and Refine lexemes in concept-windowed modes", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha"]}
        defaultSelectedSpeaker="Alpha"
        title="Run Full Pipeline"
      />,
    );

    await screen.findByTestId("transcription-run-speaker-Alpha");
    expect(screen.getByTestId("transcription-run-step-normalize")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-refine-lexemes")).toBeTruthy();

    act(() => {
      fireEvent.click(screen.getByRole("radio", { name: /all concept windows/i }));
    });

    expect(screen.queryByTestId("transcription-run-step-normalize")).toBeNull();
    expect(screen.queryByTestId("transcription-run-col-normalize")).toBeNull();
    expect(screen.queryByTestId("transcription-run-refine-lexemes")).toBeNull();

    act(() => {
      fireEvent.click(screen.getByRole("radio", { name: /edited concepts only/i }));
    });

    expect(screen.queryByTestId("transcription-run-step-normalize")).toBeNull();
    expect(screen.queryByTestId("transcription-run-col-normalize")).toBeNull();
    expect(screen.queryByTestId("transcription-run-refine-lexemes")).toBeNull();
  });

  it("renders edited-only preview rows and passes runMode on confirm", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );
    vi.mocked(getAnnotation).mockResolvedValue({
      speaker: "Alpha",
      tiers: {
        concept: {
          name: "concept",
          display_order: 0,
          intervals: [
            { start: 2, end: 3, text: "water", manuallyAdjusted: false },
            { start: 10.1, end: 11.2345, text: "hair", manuallyAdjusted: true },
            { start: 5, end: 6.7777, text: "eye", manuallyAdjusted: true },
          ],
        },
      },
    });
    const onConfirm = vi.fn<[TranscriptionRunConfirm], void>();

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={onConfirm}
        speakers={["Alpha"]}
        defaultSelectedSpeaker="Alpha"
        title="Run Full Pipeline"
      />,
    );

    await screen.findByTestId("transcription-run-speaker-Alpha");
    act(() => {
      fireEvent.click(screen.getByRole("radio", { name: /edited concepts only/i }));
    });

    expect(await screen.findByText(/#3 "eye"\s+5\.000–6\.778s/)).toBeTruthy();
    expect(screen.getByText(/#2 "hair"\s+10\.100–11\.235s/)).toBeTruthy();
    expect(screen.queryByText(/water/)).toBeNull();
    expect(screen.getByText(/Run on 2 edited concepts × 3 steps \(STT, ORTH, IPA\)/)).toBeTruthy();

    act(() => {
      fireEvent.click(screen.getByTestId("transcription-run-confirm"));
    });

    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      steps: ["stt", "ortho", "ipa"],
      runMode: "edited-only",
    }));
  });

  it("disables confirm in edited-only mode when no manually edited concepts exist", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) =>
      makeState({ speaker }),
    );
    vi.mocked(getAnnotation).mockResolvedValue({
      speaker: "Alpha",
      tiers: { concept: { name: "concept", display_order: 0, intervals: [{ start: 1, end: 2, text: "water" }] } },
    });

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha"]}
        defaultSelectedSpeaker="Alpha"
        title="Run Full Pipeline"
      />,
    );

    await screen.findByTestId("transcription-run-speaker-Alpha");
    act(() => {
      fireEvent.click(screen.getByRole("radio", { name: /edited concepts only/i }));
    });

    expect(await screen.findByText("No manually edited concepts on this speaker.")).toBeTruthy();
    expect((screen.getByTestId("transcription-run-confirm") as HTMLButtonElement).disabled).toBe(true);
  });

  it("handles getPipelineState rejection per-speaker (Test F)", async () => {
    vi.mocked(getPipelineState).mockImplementation(async (speaker: string) => {
      if (speaker === "Broken") throw new Error("network");
      return makeState({ speaker });
    });

    render(
      <TranscriptionRunModal
        open={true}
        onClose={() => {}}
        onConfirm={() => {}}
        speakers={["Alpha", "Broken", "Gamma"]}
        defaultSelectedSpeaker="Alpha"
        title="Run Full Pipeline"
      />,
    );

    // All three rows still render.
    await screen.findByTestId("transcription-run-row-Alpha");
    expect(screen.getByTestId("transcription-run-row-Broken")).toBeTruthy();
    expect(screen.getByTestId("transcription-run-row-Gamma")).toBeTruthy();

    // The broken speaker's checkbox is disabled once the rejection resolves.
    await waitFor(() => {
      const cb = screen.getByTestId(
        "transcription-run-speaker-Broken",
      ) as HTMLInputElement;
      expect(cb.disabled).toBe(true);
    });
    expect(screen.getByText(/failed to load state/)).toBeTruthy();
  });
});
