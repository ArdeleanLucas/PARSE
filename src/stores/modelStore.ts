import { create } from "zustand";
import {
  deleteModel,
  getModelBinding,
  installModelFromHf,
  installModelPack,
  listModels,
  pollCompute,
  setModelBinding,
  type InstallModelFromHfRequest,
  type ModelBinding,
  type ModelRecord,
  type ModelStage,
} from "../api/client";
import type { ComputeStatus } from "../api/types";

/** compute_type the backend registers the install job under. */
export const MODEL_INSTALL_COMPUTE_TYPE = "model_install";

export type InstallStatus = "idle" | "running" | "complete" | "error";

export interface InstallJobState {
  jobId: string | null;
  status: InstallStatus;
  /** 0..1 */
  progress: number;
  message: string | null;
  error: string | null;
}

const IDLE_INSTALL: InstallJobState = {
  jobId: null,
  status: "idle",
  progress: 0,
  message: null,
  error: null,
};

interface ModelStore {
  models: ModelRecord[];
  binding: ModelBinding;
  loading: boolean;
  error: string | null;
  install: InstallJobState;

  refresh: () => Promise<void>;
  installPack: (file: File, options?: { overwrite?: boolean }) => Promise<void>;
  installFromHf: (request: InstallModelFromHfRequest) => Promise<void>;
  remove: (id: string) => Promise<void>;
  setBinding: (stage: ModelStage, modelId: string | null) => Promise<void>;
  resetInstall: () => void;
}

const EMPTY_BINDING: ModelBinding = { stt: null, ipa: null, ortho: null };

function toMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message.trim()) return err.message;
  if (typeof err === "string" && err.trim()) return err;
  return fallback;
}

/** Normalize a poll `progress` (0..1 or 0..100) into a 0..1 fraction. */
function normalizeProgress(value: unknown): number {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n < 0) return 0;
  if (n > 1) return Math.min(1, n / 100);
  return Math.min(1, n);
}

function isComplete(status: string): boolean {
  return ["complete", "done", "success", "succeeded"].includes(status);
}

function isError(status: string): boolean {
  return ["error", "failed", "failure"].includes(status);
}

export const useModelStore = create<ModelStore>()((set, get) => {
  // Guard so overlapping poll loops from a stale install don't fight.
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function pollInstallOnce(jobId: string): Promise<void> {
    // Ignore stale timers whose job is no longer the active install.
    if (get().install.jobId !== jobId) {
      return;
    }
    let poll: ComputeStatus;
    try {
      poll = await pollCompute(MODEL_INSTALL_COMPUTE_TYPE, jobId);
    } catch (err) {
      stopPolling();
      set((s) => ({
        install: { ...s.install, status: "error", error: toMessage(err, "Install polling failed") },
      }));
      return;
    }
    if (get().install.jobId !== jobId) {
      return;
    }
    const status = String(poll.status || "running").toLowerCase();
    const progress = normalizeProgress(poll.progress);

    if (isComplete(status)) {
      stopPolling();
      set((s) => ({
        install: { ...s.install, status: "complete", progress: 1, message: null, error: null },
      }));
      // A new model exists on disk now — pull the fresh list + binding.
      await get().refresh();
      return;
    }
    if (isError(status)) {
      stopPolling();
      set((s) => ({
        install: {
          ...s.install,
          status: "error",
          progress,
          error: poll.error ?? poll.message ?? "Install failed",
        },
      }));
      return;
    }
    set((s) => ({
      install: {
        ...s.install,
        status: "running",
        progress,
        message: typeof poll.message === "string" ? poll.message : s.install.message,
      },
    }));
  }

  function startPolling(jobId: string): void {
    stopPolling();
    set({ install: { jobId, status: "running", progress: 0, message: null, error: null } });
    void pollInstallOnce(jobId);
    pollTimer = setInterval(() => {
      void pollInstallOnce(jobId);
    }, 1000);
  }

  return {
    models: [],
    binding: EMPTY_BINDING,
    loading: false,
    error: null,
    install: IDLE_INSTALL,

    refresh: async () => {
      set({ loading: true, error: null });
      try {
        const [models, binding] = await Promise.all([listModels(), getModelBinding()]);
        set({ models, binding, loading: false });
      } catch (err) {
        set({ loading: false, error: toMessage(err, "Failed to load models") });
      }
    },

    installPack: async (file, options) => {
      set({ install: { ...IDLE_INSTALL, status: "running" } });
      try {
        const { jobId } = await installModelPack(file, options);
        if (!jobId) throw new Error("Install started but returned no jobId");
        startPolling(jobId);
      } catch (err) {
        stopPolling();
        set({ install: { ...IDLE_INSTALL, status: "error", error: toMessage(err, "Install failed to start") } });
      }
    },

    installFromHf: async (request) => {
      set({ install: { ...IDLE_INSTALL, status: "running" } });
      try {
        const { jobId } = await installModelFromHf(request);
        if (!jobId) throw new Error("Install started but returned no jobId");
        startPolling(jobId);
      } catch (err) {
        stopPolling();
        set({ install: { ...IDLE_INSTALL, status: "error", error: toMessage(err, "Install failed to start") } });
      }
    },

    remove: async (id) => {
      set({ error: null });
      try {
        await deleteModel(id);
        await get().refresh();
      } catch (err) {
        set({ error: toMessage(err, "Failed to remove model") });
      }
    },

    setBinding: async (stage, modelId) => {
      set({ error: null });
      try {
        const binding = await setModelBinding(stage, modelId);
        set({ binding });
      } catch (err) {
        set({ error: toMessage(err, "Failed to update model assignment") });
      }
    },

    resetInstall: () => {
      stopPolling();
      set({ install: IDLE_INSTALL });
    },
  };
});
