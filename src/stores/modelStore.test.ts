import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelBinding, ModelRecord } from "../api/client";

const {
  mockedListModels,
  mockedGetModelBinding,
  mockedInstallModelPack,
  mockedInstallModelFromHf,
  mockedDeleteModel,
  mockedSetModelBinding,
  mockedPollCompute,
} = vi.hoisted(() => ({
  mockedListModels: vi.fn(),
  mockedGetModelBinding: vi.fn(),
  mockedInstallModelPack: vi.fn(),
  mockedInstallModelFromHf: vi.fn(),
  mockedDeleteModel: vi.fn(),
  mockedSetModelBinding: vi.fn(),
  mockedPollCompute: vi.fn(),
}));

vi.mock("../api/client", () => ({
  listModels: mockedListModels,
  getModelBinding: mockedGetModelBinding,
  installModelPack: mockedInstallModelPack,
  installModelFromHf: mockedInstallModelFromHf,
  deleteModel: mockedDeleteModel,
  setModelBinding: mockedSetModelBinding,
  pollCompute: mockedPollCompute,
}));

import { useModelStore } from "./modelStore";

const IDLE_BINDING: ModelBinding = { stt: null, ipa: null, ortho: null };

const STT_MODEL: ModelRecord = {
  id: "stt-a",
  name: "STT A",
  stage: "stt",
  format: "faster-whisper-ct2",
  engine: "faster-whisper",
  languages: ["mul"],
  source: { type: "user", ref: "user/stt-a" },
  size_bytes: 1000,
  removable: true,
  root: "user",
};

function resetStore(): void {
  useModelStore.setState({
    models: [],
    binding: IDLE_BINDING,
    loading: false,
    error: null,
    install: { jobId: null, status: "idle", progress: 0, message: null, error: null },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  resetStore();
});

afterEach(() => {
  useModelStore.getState().resetInstall();
  vi.useRealTimers();
});

describe("refresh", () => {
  it("loads models + binding in parallel and clears loading", async () => {
    mockedListModels.mockResolvedValueOnce([STT_MODEL]);
    mockedGetModelBinding.mockResolvedValueOnce({ stt: "stt-a", ipa: null, ortho: null });

    await useModelStore.getState().refresh();

    const state = useModelStore.getState();
    expect(state.models).toEqual([STT_MODEL]);
    expect(state.binding).toEqual({ stt: "stt-a", ipa: null, ortho: null });
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });

  it("records an error message on failure", async () => {
    mockedListModels.mockRejectedValueOnce(new Error("boom"));
    mockedGetModelBinding.mockResolvedValueOnce(IDLE_BINDING);

    await useModelStore.getState().refresh();

    expect(useModelStore.getState().error).toBe("boom");
    expect(useModelStore.getState().loading).toBe(false);
  });
});

describe("installPack", () => {
  it("starts the install job and polls to completion, then refreshes", async () => {
    mockedInstallModelPack.mockResolvedValueOnce({ jobId: "job-1" });
    mockedPollCompute
      .mockResolvedValueOnce({ status: "running", progress: 0.5 })
      .mockResolvedValueOnce({ status: "complete", progress: 1 });
    mockedListModels.mockResolvedValue([STT_MODEL]);
    mockedGetModelBinding.mockResolvedValue(IDLE_BINDING);

    const file = new File(["x"], "m.parsemodel");
    await useModelStore.getState().installPack(file, { overwrite: true });

    // First (immediate) poll → running/0.5.
    await vi.advanceTimersByTimeAsync(0);
    expect(useModelStore.getState().install.status).toBe("running");
    expect(useModelStore.getState().install.progress).toBe(0.5);

    // Second poll (after 1s) → complete + auto-refresh.
    await vi.advanceTimersByTimeAsync(1000);
    expect(mockedInstallModelPack).toHaveBeenCalledWith(file, { overwrite: true });
    expect(useModelStore.getState().install.status).toBe("complete");
    expect(mockedListModels).toHaveBeenCalled();
  });

  it("captures a start failure as an install error", async () => {
    mockedInstallModelPack.mockRejectedValueOnce(new Error("bad pack"));

    await useModelStore.getState().installPack(new File(["x"], "m.zip"));

    expect(useModelStore.getState().install.status).toBe("error");
    expect(useModelStore.getState().install.error).toBe("bad pack");
  });

  it("marks an error when the backend job reports failure", async () => {
    mockedInstallModelPack.mockResolvedValueOnce({ jobId: "job-2" });
    mockedPollCompute.mockResolvedValueOnce({ status: "error", progress: 0.2, error: "disk full" });

    await useModelStore.getState().installPack(new File(["x"], "m.zip"));
    await vi.advanceTimersByTimeAsync(0);

    expect(useModelStore.getState().install.status).toBe("error");
    expect(useModelStore.getState().install.error).toBe("disk full");
  });
});

describe("installFromHf", () => {
  it("starts a HF install job", async () => {
    mockedInstallModelFromHf.mockResolvedValueOnce({ jobId: "job-hf" });
    mockedPollCompute.mockResolvedValue({ status: "running", progress: 0.1 });

    await useModelStore.getState().installFromHf({
      hfRepoId: "org/model",
      stage: "stt",
      format: "faster-whisper-ct2",
    });
    await vi.advanceTimersByTimeAsync(0);

    expect(mockedInstallModelFromHf).toHaveBeenCalledWith({
      hfRepoId: "org/model",
      stage: "stt",
      format: "faster-whisper-ct2",
    });
    expect(useModelStore.getState().install.status).toBe("running");
  });
});

describe("remove", () => {
  it("deletes then refreshes", async () => {
    mockedDeleteModel.mockResolvedValueOnce({ ok: true, id: "stt-a" });
    mockedListModels.mockResolvedValue([]);
    mockedGetModelBinding.mockResolvedValue(IDLE_BINDING);

    await useModelStore.getState().remove("stt-a");

    expect(mockedDeleteModel).toHaveBeenCalledWith("stt-a");
    expect(mockedListModels).toHaveBeenCalled();
  });

  it("records an error on delete failure without refreshing", async () => {
    mockedDeleteModel.mockRejectedValueOnce(new Error("bundled models cannot be removed"));

    await useModelStore.getState().remove("bundled-x");

    expect(useModelStore.getState().error).toBe("bundled models cannot be removed");
    expect(mockedListModels).not.toHaveBeenCalled();
  });
});

describe("setBinding", () => {
  it("persists the assignment and stores the returned binding", async () => {
    mockedSetModelBinding.mockResolvedValueOnce({ stt: "stt-a", ipa: null, ortho: null });

    await useModelStore.getState().setBinding("stt", "stt-a");

    expect(mockedSetModelBinding).toHaveBeenCalledWith("stt", "stt-a");
    expect(useModelStore.getState().binding).toEqual({ stt: "stt-a", ipa: null, ortho: null });
  });

  it("passes null through to clear a binding", async () => {
    mockedSetModelBinding.mockResolvedValueOnce(IDLE_BINDING);

    await useModelStore.getState().setBinding("ipa", null);

    expect(mockedSetModelBinding).toHaveBeenCalledWith("ipa", null);
  });
});
