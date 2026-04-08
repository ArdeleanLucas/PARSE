import { create } from "zustand";
import type { ProjectConfig } from "../api/types";

interface ConfigStore {
  config: ProjectConfig | null;
  loading: boolean;
  load: () => Promise<void>;
  update: (patch: Partial<ProjectConfig>) => Promise<void>;
}

export const useConfigStore = create<ConfigStore>()(() => ({
  config: null,
  loading: false,

  // TODO Track A: implement in phase A
  load: async () => {
    throw new Error("Not implemented — Track A");
  },
  update: async (_patch: Partial<ProjectConfig>) => {
    throw new Error("Not implemented — Track A");
  },
}));
