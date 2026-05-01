// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { SpectrogramSettings } from "../SpectrogramSettings";
import {
  PRAAT_DEFAULTS,
  useSpectrogramSettings,
} from "../../../stores/useSpectrogramSettings";

describe("SpectrogramSettings", () => {
  beforeEach(() => {
    localStorage.clear();
    useSpectrogramSettings.setState({ ...PRAAT_DEFAULTS });
  });

  afterEach(() => cleanup());

  it("renders all six controls", () => {
    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={() => {}} />);

    expect(screen.getByLabelText("Window length")).toBeTruthy();
    expect(screen.getByLabelText("Dynamic range")).toBeTruthy();
    expect(screen.getByLabelText("Max frequency")).toBeTruthy();
    expect(screen.getByLabelText("Window shape")).toBeTruthy();
    expect(screen.getByLabelText("Color scheme")).toBeTruthy();
    expect(screen.getByTestId("spectrogram-pre-emphasis")).toBeTruthy();
  });

  it("Reset Praat button restores defaults", () => {
    useSpectrogramSettings.getState().set("colorScheme", "viridis");
    useSpectrogramSettings.getState().set("windowLengthSec", 0.029);
    expect(useSpectrogramSettings.getState().colorScheme).toBe("viridis");

    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("spectrogram-settings-reset"));

    const state = useSpectrogramSettings.getState();
    expect(state.colorScheme).toBe(PRAAT_DEFAULTS.colorScheme);
    expect(state.windowLengthSec).toBe(PRAAT_DEFAULTS.windowLengthSec);
  });

  it("clicking the Narrowband preset updates windowLengthSec", () => {
    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={() => {}} />);
    fireEvent.click(screen.getByTestId("spectrogram-preset-0.029"));
    expect(useSpectrogramSettings.getState().windowLengthSec).toBe(0.029);
  });

  it("Escape key fires onClose", () => {
    const onClose = vi.fn();
    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking outside fires onClose", () => {
    const onClose = vi.fn();
    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={onClose} />);
    fireEvent.mouseDown(document.body);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking inside the dialog does not fire onClose", () => {
    const onClose = vi.fn();
    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={onClose} />);
    fireEvent.mouseDown(screen.getByTestId("spectrogram-settings"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("toggling pre-emphasis writes 50 or 0 to preEmphasisHz", () => {
    render(<SpectrogramSettings anchor={{ x: 100, y: 100 }} onClose={() => {}} />);
    const checkbox = screen.getByTestId("spectrogram-pre-emphasis") as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    fireEvent.click(checkbox);
    expect(useSpectrogramSettings.getState().preEmphasisHz).toBe(0);
    fireEvent.click(checkbox);
    expect(useSpectrogramSettings.getState().preEmphasisHz).toBe(50);
  });
});
