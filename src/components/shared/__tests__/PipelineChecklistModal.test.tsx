// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { PipelineChecklistModal, type PipelineChecklistResult } from "../PipelineChecklistModal";

vi.mock("../../../api/client", () => ({
  getPipelineState: vi.fn(),
}));

import { getPipelineState } from "../../../api/client";

const FAKE_STATE = {
  speaker: "Fail02",
  normalize: { done: true, path: "audio/working/Fail02/Fail02.wav" },
  stt: { done: false, segments: 0 },
  ortho: { done: true, intervals: 42 },
  ipa: { done: false, intervals: 0 },
};

describe("PipelineChecklistModal", () => {
  beforeEach(() => {
    vi.mocked(getPipelineState).mockReset();
  });
  afterEach(() => {
    cleanup();
  });

  it("renders one row per pipeline step with current state", async () => {
    vi.mocked(getPipelineState).mockResolvedValueOnce(FAKE_STATE);

    render(
      <PipelineChecklistModal
        open={true}
        speaker="Fail02"
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );

    await waitFor(() =>
      expect(screen.getByTestId("pipeline-step-normalize")).toBeTruthy(),
    );

    expect(screen.getByTestId("pipeline-step-stt")).toBeTruthy();
    expect(screen.getByTestId("pipeline-step-ortho")).toBeTruthy();
    expect(screen.getByTestId("pipeline-step-ipa")).toBeTruthy();
    expect(screen.getByText(/42 intervals/)).toBeTruthy();
  });

  it("defaults selected steps to those not yet done", async () => {
    vi.mocked(getPipelineState).mockResolvedValueOnce(FAKE_STATE);

    render(
      <PipelineChecklistModal
        open={true}
        speaker="Fail02"
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );

    const normalizeCheckbox = await screen.findByTestId("pipeline-step-normalize") as HTMLInputElement;
    const sttCheckbox = screen.getByTestId("pipeline-step-stt") as HTMLInputElement;
    const orthoCheckbox = screen.getByTestId("pipeline-step-ortho") as HTMLInputElement;
    const ipaCheckbox = screen.getByTestId("pipeline-step-ipa") as HTMLInputElement;

    // Already done → off; not done → on.
    expect(normalizeCheckbox.checked).toBe(false);
    expect(sttCheckbox.checked).toBe(true);
    expect(orthoCheckbox.checked).toBe(false);
    expect(ipaCheckbox.checked).toBe(true);
  });

  it("passes ticked steps and implicit overwrite flags to onConfirm", async () => {
    vi.mocked(getPipelineState).mockResolvedValueOnce(FAKE_STATE);

    const onConfirm = vi.fn<[PipelineChecklistResult], void>();
    render(
      <PipelineChecklistModal
        open={true}
        speaker="Fail02"
        onClose={() => {}}
        onConfirm={onConfirm}
      />,
    );

    // Wait for state to load, then tick ortho (which is already done) so the
    // confirm should carry `overwrites.ortho = true`.
    const orthoCheckbox = await screen.findByTestId("pipeline-step-ortho") as HTMLInputElement;
    act(() => { fireEvent.click(orthoCheckbox); });

    const runButton = screen.getByTestId("pipeline-checklist-run");
    act(() => { fireEvent.click(runButton); });

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const result = onConfirm.mock.calls[0][0];
    // stt (default-on) + ipa (default-on) + ortho (user-ticked) — but
    // normalize was default-off, so excluded.
    expect(result.steps).toEqual(["stt", "ortho", "ipa"]);
    expect(result.overwrites.ortho).toBe(true);
    expect(result.overwrites.stt).toBeUndefined();
    expect(result.overwrites.ipa).toBeUndefined();
  });

  it("disables Run when nothing is selected", async () => {
    vi.mocked(getPipelineState).mockResolvedValueOnce({
      ...FAKE_STATE,
      normalize: { done: true, path: "x" },
      stt: { done: true, segments: 1 },
      ortho: { done: true, intervals: 1 },
      ipa: { done: true, intervals: 1 },
    });

    render(
      <PipelineChecklistModal
        open={true}
        speaker="Fail02"
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );

    // Everything is done → default selection is empty → Run is disabled.
    const runButton = await screen.findByTestId("pipeline-checklist-run") as HTMLButtonElement;
    expect(runButton.disabled).toBe(true);
  });

  it("surfaces a fetch error", async () => {
    vi.mocked(getPipelineState).mockRejectedValueOnce(new Error("boom"));

    render(
      <PipelineChecklistModal
        open={true}
        speaker="Fail02"
        onClose={() => {}}
        onConfirm={() => {}}
      />,
    );

    await waitFor(() => expect(screen.getByText(/boom/)).toBeTruthy());
  });
});
