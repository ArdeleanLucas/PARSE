// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelBinding, ModelRecord } from "../../api/client";
import type { InstallJobState } from "../../stores/modelStore";

// The store is mocked so the component test drives pure UI behavior without a
// live backend. `useModelStore((s) => ...)` selectors run against `fakeState`.
const actions = {
  refresh: vi.fn(),
  installPack: vi.fn(),
  installFromHf: vi.fn(),
  remove: vi.fn(),
  setBinding: vi.fn(),
  resetInstall: vi.fn(),
};

let fakeState: Record<string, unknown>;

vi.mock("../../stores/modelStore", () => ({
  useModelStore: (selector: (s: Record<string, unknown>) => unknown) => selector(fakeState),
}));

import { ModelsManager } from "./ModelsManager";

const IDLE_INSTALL: InstallJobState = {
  jobId: null,
  status: "idle",
  progress: 0,
  message: null,
  error: null,
};

const IDLE_BINDING: ModelBinding = { stt: null, ipa: null, ortho: null };

const STT_USER: ModelRecord = {
  id: "stt-user",
  name: "User STT",
  stage: "stt",
  format: "faster-whisper-ct2",
  engine: "faster-whisper",
  languages: ["mul"],
  source: { type: "user", ref: "user/stt" },
  size_bytes: 1024 * 1024 * 500,
  removable: true,
  root: "user",
};

const IPA_BUNDLED: ModelRecord = {
  id: "ipa-bundled",
  name: "Bundled IPA",
  stage: "ipa",
  format: "hf-transformers",
  engine: "wav2vec2",
  languages: ["mul"],
  source: { type: "bundled", ref: "bundled/ipa" },
  size_bytes: 1024 * 1024 * 1200,
  removable: false,
  root: "bundled",
};

function setState(overrides: Partial<typeof fakeState> = {}): void {
  fakeState = {
    models: [],
    binding: IDLE_BINDING,
    loading: false,
    error: null,
    install: IDLE_INSTALL,
    ...actions,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  setState();
});

afterEach(() => {
  cleanup();
});

describe("ModelsManager", () => {
  it("refreshes on open", () => {
    render(<ModelsManager open onClose={vi.fn()} />);
    expect(actions.refresh).toHaveBeenCalled();
  });

  it("renders installed models with a source badge and human size", () => {
    setState({ models: [STT_USER, IPA_BUNDLED] });
    render(<ModelsManager open onClose={vi.fn()} />);

    const row = screen.getByTestId("model-row-stt-user");
    // The user model name appears in its row (it also appears as a <select>
    // option, hence the row-scoped lookup).
    expect(row.textContent).toContain("User STT");
    // Source badges are present.
    expect(screen.getByText("User")).toBeTruthy();
    expect(screen.getByText("Bundled")).toBeTruthy();
    // 500 MB rendered from size_bytes.
    expect(row.textContent).toContain("500 MB");
  });

  it("shows a Remove button only for removable models", () => {
    setState({ models: [STT_USER, IPA_BUNDLED] });
    render(<ModelsManager open onClose={vi.fn()} />);

    expect(screen.queryByTestId("model-remove-stt-user")).toBeTruthy();
    expect(screen.queryByTestId("model-remove-ipa-bundled")).toBeNull();
  });

  it("requires a confirm before removing a user model", () => {
    setState({ models: [STT_USER] });
    render(<ModelsManager open onClose={vi.fn()} />);

    fireEvent.click(screen.getByTestId("model-remove-stt-user"));
    expect(actions.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("model-remove-confirm-stt-user"));
    expect(actions.remove).toHaveBeenCalledWith("stt-user");
  });

  it("assigns a model to a stage via the binding dropdown", () => {
    setState({ models: [STT_USER] });
    render(<ModelsManager open onClose={vi.fn()} />);

    fireEvent.change(screen.getByTestId("model-binding-stt"), {
      target: { value: "stt-user" },
    });
    expect(actions.setBinding).toHaveBeenCalledWith("stt", "stt-user");
  });

  it("filters each stage dropdown to only its own stage models", () => {
    setState({ models: [STT_USER, IPA_BUNDLED] });
    render(<ModelsManager open onClose={vi.fn()} />);

    // The STT select offers the STT model but NOT the IPA model.
    const sttSelect = screen.getByTestId("model-binding-stt") as HTMLSelectElement;
    const sttValues = Array.from(sttSelect.options).map((o) => o.value);
    expect(sttValues).toContain("stt-user");
    expect(sttValues).not.toContain("ipa-bundled");

    // The IPA select offers the IPA model but NOT the STT model.
    const ipaSelect = screen.getByTestId("model-binding-ipa") as HTMLSelectElement;
    const ipaValues = Array.from(ipaSelect.options).map((o) => o.value);
    expect(ipaValues).toContain("ipa-bundled");
    expect(ipaValues).not.toContain("stt-user");
  });

  it("clears a binding when Unassigned is chosen", () => {
    setState({ models: [STT_USER], binding: { stt: "stt-user", ipa: null, ortho: null } });
    render(<ModelsManager open onClose={vi.fn()} />);

    fireEvent.change(screen.getByTestId("model-binding-stt"), { target: { value: "" } });
    expect(actions.setBinding).toHaveBeenCalledWith("stt", null);
  });

  it("shows a first-run STT CTA when no STT model is installed and prefills the HF form", () => {
    setState({ models: [IPA_BUNDLED] });
    render(<ModelsManager open onClose={vi.fn()} />);

    const cta = screen.getByTestId("models-no-stt-cta");
    expect(cta).toBeTruthy();
    fireEvent.click(screen.getByText("Install standard STT model"));
    // Switches to the HF tab with the repo prefilled.
    const repoInput = screen.getByTestId("hf-repo-input") as HTMLInputElement;
    expect(repoInput.value).toBe("razhan/whisper-base-sdh");
  });

  it("hides the first-run CTA once an STT model exists", () => {
    setState({ models: [STT_USER] });
    render(<ModelsManager open onClose={vi.fn()} />);
    expect(screen.queryByTestId("models-no-stt-cta")).toBeNull();
  });

  it("installs from a chosen pack file", () => {
    render(<ModelsManager open onClose={vi.fn()} />);
    const input = screen.getByTestId("model-pack-input") as HTMLInputElement;
    const file = new File(["x"], "m.parsemodel");
    fireEvent.change(input, { target: { files: [file] } });
    expect(actions.installPack).toHaveBeenCalledWith(file);
  });

  it("installs from HuggingFace with the entered fields", () => {
    render(<ModelsManager open onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId("add-mode-hf"));
    fireEvent.change(screen.getByTestId("hf-repo-input"), { target: { value: "org/model" } });
    fireEvent.change(screen.getByTestId("hf-stage-select"), { target: { value: "ortho" } });
    fireEvent.change(screen.getByTestId("hf-format-select"), { target: { value: "hf-transformers" } });
    fireEvent.click(screen.getByTestId("hf-install-button"));

    expect(actions.installFromHf).toHaveBeenCalledWith({
      hfRepoId: "org/model",
      stage: "ortho",
      format: "hf-transformers",
      name: undefined,
    });
  });

  it("renders install progress while running", () => {
    setState({
      install: { jobId: "j1", status: "running", progress: 0.42, message: "Downloading", error: null },
    });
    render(<ModelsManager open onClose={vi.fn()} />);
    const status = screen.getByTestId("install-status");
    expect(status.textContent).toContain("Downloading");
    expect(status.textContent).toContain("42%");
  });

  it("surfaces an install error with a dismiss control", () => {
    setState({
      install: { jobId: "j1", status: "error", progress: 0.1, message: null, error: "disk full" },
    });
    render(<ModelsManager open onClose={vi.fn()} />);
    expect(screen.getByTestId("install-error").textContent).toContain("disk full");
  });

  it("does not refresh when closed", () => {
    render(<ModelsManager open={false} onClose={vi.fn()} />);
    expect(actions.refresh).not.toHaveBeenCalled();
  });
});
